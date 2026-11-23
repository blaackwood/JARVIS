#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <mmsystem.h>
#include <onnxruntime_cxx_api.h>
#include <algorithm>
#include <array>
#include <cstdint>
#include <deque>
#include <iostream>
#include <fstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <chrono>
#include <vector>
#pragma comment(lib, "winmm.lib")
namespace {
constexpr int RATE=16000, BLOCK=1280, MEL=32, MW=76, EMB=96, FW=16;
constexpr float THRESHOLD=0.62f;
struct Models {
 Ort::Env env{ORT_LOGGING_LEVEL_ERROR,"JarvisWakeNative"};
 Ort::SessionOptions opt;
 Ort::Session mel{nullptr}, embedding{nullptr}, wake{nullptr};
 Ort::MemoryInfo mem{Ort::MemoryInfo::CreateCpu(OrtArenaAllocator,OrtMemTypeDefault)};
 explicit Models(const std::wstring& p) {
  opt.SetIntraOpNumThreads(1); opt.SetInterOpNumThreads(1);
  opt.SetExecutionMode(ExecutionMode::ORT_SEQUENTIAL);
  opt.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
  opt.DisableMemPattern();
  mel=Ort::Session(env,(p+L"\\melspectrogram.onnx").c_str(),opt);
  embedding=Ort::Session(env,(p+L"\\embedding_model.onnx").c_str(),opt);
  wake=Ort::Session(env,(p+L"\\hey_jarvis_v0.1.onnx").c_str(),opt);
 }
 std::vector<float> runMel(const std::vector<int16_t>& pcm) {
  std::vector<float> x(pcm.begin(),pcm.end()); int64_t sh[]={1,(int64_t)x.size()};
  auto t=Ort::Value::CreateTensor<float>(mem,x.data(),x.size(),sh,2);
  const char* in[]={"input"}; const char* out[]={"output"};
  auto y=mel.Run(Ort::RunOptions{nullptr},in,&t,1,out,1);
  auto n=y[0].GetTensorTypeAndShapeInfo().GetElementCount();
  const float* v=y[0].GetTensorData<float>(); std::vector<float> z(v,v+n);
  for(auto& a:z) a=a/10.0f+2.0f;
  if(z.size()%MEL) throw std::runtime_error("bad mel output");
  return z;
 }
 std::array<float,EMB> runEmbedding(const std::array<float,MW*MEL>& x) {
  int64_t sh[]={1,MW,MEL,1};
  auto t=Ort::Value::CreateTensor<float>(mem,const_cast<float*>(x.data()),x.size(),sh,4);
  const char* in[]={"input_1"}; const char* out[]={"conv2d_19"};
  auto y=embedding.Run(Ort::RunOptions{nullptr},in,&t,1,out,1);
  std::array<float,EMB> z{}; std::copy_n(y[0].GetTensorData<float>(),EMB,z.begin()); return z;
 }
 float runWake(const std::array<float,FW*EMB>& x) {
  int64_t sh[]={1,FW,EMB};
  auto t=Ort::Value::CreateTensor<float>(mem,const_cast<float*>(x.data()),x.size(),sh,3);
  const char* in[]={"x.1"}; const char* out[]={"53"};
  auto y=wake.Run(Ort::RunOptions{nullptr},in,&t,1,out,1); return y[0].GetTensorData<float>()[0];
 }
};
class Detector {
 Models m; std::deque<int16_t> raw; std::deque<float> mel,features; int warm=0,hits=0; bool wake=false;
public:
 explicit Detector(const std::wstring& p):m(p){mel.assign(MW*MEL,1.0f);features.assign(FW*EMB,0.0f);}
 bool takeWake(){bool v=wake;wake=false;return v;}
 float process(const int16_t* pcm,size_t n) {
  for(size_t i=0;i<n;++i) raw.push_back(pcm[i]); while(raw.size()>160000)raw.pop_front();
  size_t take=std::min(raw.size(),n+480); std::vector<int16_t> clip;
  auto b=raw.end()-(ptrdiff_t)take; clip.assign(b,raw.end());
  auto spec=m.runMel(clip); for(float v:spec)mel.push_back(v);
  while(mel.size()>970*MEL)mel.pop_front();
  if(mel.size()<MW*MEL)return 0;
  std::array<float,MW*MEL> w{};std::copy(mel.end()-w.size(),mel.end(),w.begin());
  auto e=m.runEmbedding(w);for(float v:e)features.push_back(v);
  while(features.size()>120*EMB)features.pop_front();
  if(warm++<16)return 0;
  std::array<float,FW*EMB> f{};std::copy(features.end()-f.size(),features.end(),f.begin());
  float score=m.runWake(f);hits=score>=THRESHOLD?hits+1:0;
  if(hits>=3){wake=true;std::cout<<"WAKE_DETECTED score="<<score<<std::endl;hits=0;}
  return score;
 }
};
void capture(Detector& d, DWORD maxSeconds=0) {
 WAVEFORMATEX fmt{};fmt.wFormatTag=WAVE_FORMAT_PCM;fmt.nChannels=1;fmt.nSamplesPerSec=RATE;
 fmt.wBitsPerSample=16;fmt.nBlockAlign=2;fmt.nAvgBytesPerSec=RATE*2;
 HANDLE ev=CreateEventW(nullptr,FALSE,FALSE,nullptr);if(!ev)throw std::runtime_error("CreateEvent failed");
 HWAVEIN h=nullptr;MMRESULT r=waveInOpen(&h,WAVE_MAPPER,&fmt,(DWORD_PTR)ev,0,CALLBACK_EVENT);
 if(r!=MMSYSERR_NOERROR){CloseHandle(ev);throw std::runtime_error("waveInOpen "+std::to_string(r));}
 std::array<std::array<int16_t,BLOCK>,3> data{};std::array<WAVEHDR,3> hdr{};
 for(size_t i=0;i<hdr.size();++i){hdr[i].lpData=(LPSTR)data[i].data();hdr[i].dwBufferLength=sizeof(data[i]);waveInPrepareHeader(h,&hdr[i],sizeof(WAVEHDR));waveInAddBuffer(h,&hdr[i],sizeof(WAVEHDR));}
 r=waveInStart(h);if(r!=MMSYSERR_NOERROR)throw std::runtime_error("waveInStart "+std::to_string(r));
 std::cout<<"MIC_ACTIVE 16kHz mono"<<std::endl;int count=0;ULONGLONG started=GetTickCount64();
 while(true){DWORD wait=MsgWaitForMultipleObjects(1,&ev,FALSE,1000,QS_ALLINPUT);if(wait==WAIT_TIMEOUT){if(maxSeconds&&GetTickCount64()-started>=maxSeconds*1000ULL)break;continue;}if(wait!=WAIT_OBJECT_0)continue;
  for(size_t i=0;i<hdr.size();++i){auto& x=hdr[i];if(!(x.dwFlags&WHDR_DONE))continue;
   size_t n=x.dwBytesRecorded/2;if(n){float s=d.process(data[i].data(),n);if(++count%25==0)std::cout<<"score="<<s<<std::endl;}
   x.dwBytesRecorded=0;x.dwFlags&=~WHDR_DONE;waveInAddBuffer(h,&x,sizeof(WAVEHDR));
  }
  if((GetAsyncKeyState(VK_ESCAPE)&0x8000)||(maxSeconds&&GetTickCount64()-started>=maxSeconds*1000ULL))break;
 }
 waveInStop(h);waveInReset(h);for(auto& x:hdr)waveInUnprepareHeader(h,&x,sizeof(WAVEHDR));waveInClose(h);CloseHandle(ev);
}
}
#ifndef JARVIS_WAKE_DAEMON
int wmain(int argc,wchar_t** argv){
 try{
  SetPriorityClass(GetCurrentProcess(),BELOW_NORMAL_PRIORITY_CLASS);SetThreadPriority(GetCurrentThread(),THREAD_PRIORITY_BELOW_NORMAL);
  std::wstring p=argc>1?argv[1]:L".";std::wcout<<L"JARVIS native detector | "<<p<<std::endl;Detector d(p);
  if(argc>2&&std::wstring(argv[2])==L"--self-test"){std::array<int16_t,BLOCK> z{};for(int i=0;i<40;++i)d.process(z.data(),z.size());std::cout<<"SELF_TEST_OK"<<std::endl;return 0;}
  if(argc>2&&std::wstring(argv[2])==L"--bench"){std::array<int16_t,BLOCK> z{};for(int i=0;i<750;++i){d.process(z.data(),z.size());std::this_thread::sleep_for(std::chrono::milliseconds(80));}std::cout<<"BENCH_OK"<<std::endl;return 0;}
  if(argc>3&&std::wstring(argv[2])==L"--pcm"){std::ifstream f(argv[3],std::ios::binary);if(!f)throw std::runtime_error("cannot open PCM fixture");std::array<int16_t,BLOCK> b{};int frames=0;while(f.read(reinterpret_cast<char*>(b.data()),sizeof(b))||f.gcount()>0){size_t n=(size_t)f.gcount()/sizeof(int16_t);if(n){float score=d.process(b.data(),n);if((++frames%10)==0)std::cout<<"FRAME "<<frames<<" SCORE "<<score<<std::endl;}}std::cout<<"PCM_TEST_OK frames="<<frames<<std::endl;return 0;}
  if(argc>2&&std::wstring(argv[2])==L"--listen-test"){capture(d,15);return 0;}
  capture(d);return 0;
 }catch(const Ort::Exception& e){std::cerr<<"ONNX_ERROR: "<<e.what()<<std::endl;return 10;}
 catch(const std::exception& e){std::cerr<<"ERROR: "<<e.what()<<std::endl;return 11;}
}
#endif // JARVIS_WAKE_DAEMON

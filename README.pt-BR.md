# JARVIS

**Assistente pessoal de desktop criado por blaackwood.**

English: [README.md](README.md)

O JARVIS é um assistente de desktop com interface holográfica, conversa por
voz em tempo real, controle do computador e navegador, ferramentas
especializadas, fluxos de programação, memória persistente, tarefas agendadas,
aulas visuais e integrações remotas opcionais.

O motor principal de conversa é o Google Gemini Live. Cada instalação precisa
ser configurada com a chave de API Gemini do próprio usuário. Este repositório
não contém a chave do desenvolvedor, memória pessoal, histórico de conversas
ou configurações privadas da instalação original.

## Veja em ação

<p align="center">
  <img src="docs/media/demo-solar-system.gif" alt="Aula visual 3D do JARVIS: sistema solar com planetas, lua e rótulos em órbita" width="49%">
  <img src="docs/media/demo-atom.gif" alt="Aula visual 3D do JARVIS: átomo com núcleo e elétrons em órbita" width="49%">
</p>

<p align="center"><em>Aulas 3D interativas renderizadas pelo quadro visual holográfico do
próprio JARVIS (capturadas do renderizador real). Peça qualquer assunto e o JARVIS
monta a cena enquanto explica; arraste para girar e use ESC para limpar.</em></p>

## Funcionalidades

- **Voz e conversa:** conversas ao vivo, respostas faladas, seleção de voz e
  dispositivos de áudio, push-to-talk, controle do microfone e ativação
  opcional por palavra-chave local.
- **Controle do computador:** inspeção da janela ativa, interação com
  controles acessíveis, mouse e teclado, captura de tela, gerenciamento de
  janelas e marcações visuais na área de trabalho.
- **Arquivos:** abrir, ler, pesquisar, criar, mover, copiar, renomear e excluir
  arquivos; analisar arquivos selecionados ou arrastados para o JARVIS.
- **Navegação:** abrir e controlar páginas, pesquisar na web, clicar, digitar,
  rolar, ler conteúdo, gerenciar abas e consultar clima e voos.
- **Programação:** explicar, editar e criar código, trabalhar em projetos
  existentes com agentes e executar verificações.
- **Memória e organização:** histórico local de conversas, memória semântica,
  contexto de projetos, lembretes, rotinas, sessões de foco e tarefas em
  segundo plano.
- **Aulas visuais:** cenas holográficas 3D, diagramas, aulas guiadas e três
  ferramentas distintas para xadrez: assistente, treinador e professor.
- **Extensões:** Skills de terceiros com suas próprias licenças, provedores,
  GitHub, Cloudflare, painel remoto e agente desktop.

A lista completa das ferramentas está em FEATURES.md. A origem e a licença
de cada Skill estão em SKILLS.md.

## Instalação e primeira configuração

1. Instale Python 3.11 a 3.13 (Python 3.13 é a versão usada nos testes) e Git.
2. Clone o repositório e entre na pasta.
3. No PowerShell:

   ~~~powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   $env:PYTHONUTF8 = "1"
   python setup.py
   python main.py
   ~~~

4. Na primeira abertura, o JARVIS pede a chave Gemini pessoal. Crie a chave
   no Google AI Studio (https://aistudio.google.com/apikey), informe-a na
   tela e valide. A interface principal só é liberada depois que o Google
   aceitar a chave.

A chave fica em config/api_keys.json. Esse arquivo é ignorado pelo Git, mas
o armazenamento atual é em texto simples. Proteja sua conta do sistema
operacional e nunca compartilhe, anexe a issues ou publique esse arquivo.
O uso e eventuais cobranças da API pertencem à sua própria conta Google.

Consulte INSTALLATION.md para instruções detalhadas e recursos opcionais.

## Recursos opcionais

Alguns recursos precisam de configuração independente: Stockfish para xadrez,
OpenCode/Codex para agentes de programação, conta Cloudflare para lembretes
remotos, pareamento do painel remoto, modelos locais de voz e credenciais
específicas de outros provedores. A chave Gemini não substitui essas
configurações.

## Privacidade e segurança

O JARVIS executa as ferramentas do computador localmente, mas não é totalmente
offline. A conversa por voz usa o serviço Gemini do Google. O processador de
arquivos envia ao modelo Gemini o arquivo que o usuário selecionou
explicitamente. Outros provedores e integrações em nuvem recebem os dados
necessários à ação solicitada.

O projeto possui controles de autorização e confirmações para operações
sensíveis. Leia SECURITY.md antes de habilitar automações.

Nenhuma chave, memória pessoal, conversa, fila de tarefas, dados de projetos
privados, logs ou capturas de tela da instalação original é distribuída aqui.

## Plataformas

O instalador de dependências contempla Windows, macOS e Linux, mas alguns
recursos dependem do sistema operacional. O fluxo completo de desktop e o
instalador são desenvolvidos principalmente para Windows 10/11. O daemon
nativo de palavra-chave e a automação Windows UIA são exclusivos do Windows.

## Licença e autoria

O código original do JARVIS está sob a licença MIT (LICENSE), copyright
blaackwood. Skills, bibliotecas, ferramentas, motores e ativos de terceiros
mantêm suas próprias licenças e titulares. Consulte
THIRD_PARTY_NOTICES.md e SKILLS.md.

A licença MIT do JARVIS não altera nem substitui as licenças de terceiros.

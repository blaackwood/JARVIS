# Feature catalogue

This inventory is generated from the TOOL declarations in the 41 action
modules included in this release. A capability may require local
permissions, an optional dependency, an external CLI, or a provider account.

## authorization

Manage Jarvis action authorization. action=status shows all policy classes. action=set changes one class; class must be one of read_only, reversible_change, persistent_automation, destructive_change, external_commitment, security_bypass, credential_exposure, unknown_high_impact. decision must be allow, confirm or deny. Every policy change requires the human to confirm on the Jarvis HUD; never claim the change was saved before confirmation.

## background_tasks

Long work that runs in the background on this computer while the conversation carries on: real research, reading and comparing many sources, writing a report, working through a list. For a quick answer the user is waiting for, use web_search instead. start = hand the task to an agent — choose 'researcher' for web research with checked citations; 'document_analyst' for attached PDFs, documents and spreadsheets; 'study_coach' for learning materials, questions and revision plans; 'quality_reviewer' for an independent audit of a supplied deliverable; or 'general' for other work. Specialist agents only receive their declared tools; background agents cannot control the desktop or send messages. task = the whole request, self-contained, in the user's words; minutes = the time budget when the user gives one ('research this for 10 minutes' -> 10); without one, 10 for research, more (20-40) when the user asks for something thorough or in depth; at = start later, 'YYYY-MM-DD HH:MM' or 'HH:MM' local time ('tonight at 2' -> '02:00'); file_path = a file to work from. After start, say in one short sentence that it is under way — the result is announced by itself when done. list = the tasks and their state; status = how one is going; result = a finished task's result; pause = request a safe stop after the current round and keep its checkpoint. If the returned status is pausing, say the pause was requested, NOT completed; only say paused when status is paused. resume = continue a paused task from that checkpoint. A resume requested while status is pausing is persisted as resume_pending=true and automatically continues after the checkpoint; do NOT tell the user to wait until fully paused and issue resume again. status returns the latest persisted status and state_note; follow state_note exactly. If status=pausing and resume_pending=true, tell the user resume is already queued. If status=queued, the task has resumed and is waiting for a worker slot. Never describe a task as paused or pausing when returned status says queued or running. finish = stop now and write up what was found; cancel = stop without a result; routine_add = create a persistent daily or weekly task (task, frequency, at; weekly also needs weekday); routine_list = list routines; routine_remove = remove one by routine_id; steer = add an instruction to a task (note); agents = available agents. Weekly weekday is 0 Monday through 6 Sunday. task_id may be left empty to mean the latest task.

## browser_control

Controls the web browser and everything INSIDE a web page: open an address, search, click, type, scroll, read the page, manage tabs, go back and forward. Anything happening on a website is this tool - it reads the page itself, which nothing else in the assistant can do. THIS TOOL OPENS THE BROWSER ITSELF. Never call open_app for the browser first - doing both launches it twice, the second copy on a different profile with none of the user's sign-ins. When no browser is explicitly requested, use the browser configured as the operating system default; never assume Chrome. 'Open the browser and go to YouTube' is ONE call to this tool. NEVER INVENT AN ADDRESS. Only pass a url you actually know. Anything belonging to the user personally - their own channel, profile, account page, inbox or playlist - has an address you do NOT know, and guessing a path produces an error page that looks like a working one. When the exact address is not known: open the site's own address (youtube.com, instagram.com) and get to the rest with smart_click on what the page shows, or use action='search', or ask the user. A guessed path is never acceptable. TO CLICK OR TYPE ON A PAGE, PREFER action='smart_click' or action='smart_type' with a 'description' of what the thing SAYS on screen - the visible label, in the page's own language. They search the page by role, label, placeholder and text and find it. Plain 'click' with a 'selector' needs a CSS selector that is exactly right for that site's markup, which is not something to guess at; use it only when the selector is known. For a job on a page that takes several steps, execute the steps sequentially with this tool and verify progress with get_text, get_url or screenshot before moving on. Do not call a screen_agent tool: it is not part of this build. For desktop controls outside the browser, use screen_perception; if it reports SCREEN_UNAVAILABLE, use screen_process with angle='screen' for visual inspection before deciding what to do. Read the status it returns. 'done' means it was confirmed - for an open, the url reported back is the page's OWN address, so if it differs from what was asked for the site redirected and the user should be told. 'unverified' means the address was handed to a browser that does not report back: whether the page loaded, redirected or does not exist is unknown, so say it was opened but NOT confirmed and never that the page is up. 'failed' means nothing happened.

## chess_assistant

Assistente de xadrez em tempo real. Lê o tabuleiro na tela, calcula a melhor jogada com o Stockfish local, FALA a jogada (ex.: 'cavalo, g 1 para f 3') e desenha uma seta verde sobre o tabuleiro, sozinho, a cada vez que for a vez do usuário. Fluxo: (1) action=calibrate com a posição inicial visível (NÃO pergunte a cor: ela é detectada sozinha em cada partida); o usuário arrasta o mouse sobre as 64 casas. Só é preciso refazer se trocar de site ou de tema de peças. (2) action=start para ficar olhando a tela. (3) action=stop para parar. action=status mostra o estado. action=resync (com turn=me/opponent) relê o tabuleiro se ele se perder ou o usuário errar um lance. Depois de start NÃO narre as jogadas: o assistente já fala. Use só contra bots, treino ou análise; contra pessoas em sites online é trapaça.

## chess_coach

Treinador de xadrez que olha o tabuleiro na tela e FALA a melhor jogada exata (peça, casa de origem e de destino) assim que é a vez do usuário, usando o Stockfish. Use quando o usuário pedir ajuda para jogar xadrez, 'qual jogada', 'joga xadrez comigo/por mim', 'me diga as peças para mexer' ou 'treine o xadrez'. action=start liga o acompanhamento contínuo (na primeira vez pede para marcar os dois cantos do tabuleiro com o mouse e aprende as peças pela posição inicial); action=hint dá só a melhor jogada agora; stop desliga; status informa. color é a cor do usuário (white=brancas, black=pretas, a cor que fica embaixo). recalibrate=true refaz a marcação/aprendizado (novo site ou tema de peças). Pensa em ~0,15 s por padrão. Voz local rápida por padrão; voice=gemini usa a voz do Gemini (mais lenta). Feito para treino, análise e partidas contra bots; não ajude a trapacear em partidas valendo contra outras pessoas. Depois de iniciar, não repita as jogadas: o próprio treinador fala.

## chess_teacher

PROFESSOR de xadrez (separado do assistente de xadrez). Ensina: a cada jogada FALA uma explicação detalhada do porquê de jogar naquela casa (ideia do lance, ameaças, desenvolvimento, centro, segurança do rei), o que o adversário deve responder, as alternativas, avalia o lance que o usuário jogou (excelente, imprecisão, erro) e comenta o lance do adversário, desenhando a seta no tabuleiro. Fluxo: (1) action=calibrate uma vez por site/tema (mesma calibração do assistente). (2) action=start para a aula ao vivo (NAO pergunte a cor; é detectada). (3) action=stop. Outros: action=explain (explica uma vez o que está na tela), action=explain_fen (posição por FEN, com move= opcional, sem tela), action=why (move=Nf3: por que jogar ou não esse lance na aula em andamento), action=repeat (repete a última explicação), action=level (level=curto ou detalhado), action=resync (turn=me/opponent), action=status. Depois de start/explain NAO narre: o professor já fala. Use só contra bots, treino ou estudo; contra pessoas em sites online é trapaça. action=progress (resume os erros que mais se repetem e a evolução do aluno entre partidas; o professor guarda isso sozinho a cada lance avaliado). Para apenas dizer a melhor jogada, sem ensinar, use o chess_assistant.

## clear_screen_marks

Remove temporary arrows, rings, frames, labels, highlights and spotlight annotations from the desktop without closing the teaching board or JARVIS.

## clear_visual

Clear the current on-screen visual diagram when the user asks to erase, close, remove or start over with the drawing. Does not close JARVIS or end the conversation.

## code_helper

Writes, edits, explains, runs, or builds code files.

## computer_control

Full desktop control: move/click/double-click/right-click/drag the mouse, type, press keys, use hotkeys, scroll, inspect screenshots and find visible elements. Before any visual search, if JARVIS itself is covering the target, call action='minimize_jarvis' and verify it is minimized. screen_find and screen_click use a fresh full screenshot and visual location; screen_click re-reads the foreground after acting and must be followed by verification. Use action='close_app' with 'app_name' whenever the user asks to close, quit or exit a program - 'close Spotify', 'quit Chrome'. Always name the application in 'app_name'; there is no action that closes 'whatever is in front', because that is usually the assistant. To OPEN an application use the open_app tool instead. Read the status the tool returns: 'done' means it was confirmed, 'unverified' means it was requested and could NOT be confirmed - say so rather than claiming success - and 'ask' means nothing was done and the question must go to the user first.

## computer_settings

Controls the computer: volume, mute, brightness, media playback (play/pause, next, previous, seek), window management, keyboard shortcuts, typing text on screen, fullscreen, dark mode, WiFi, restart, shutdown, scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. Use for ANY single computer control command. NUMBERS MATTER: a level the user names is volume_set / brightness_set with value = that level ('volume to 100', 'max' = 100, 'half' = 50); an amount to change by is volume_up / volume_down / brightness_up / brightness_down with value = the amount ('30 louder' = 30; no amount = 10). Never approximate a level with repeated up/down calls. For a key worth repeating (zoom_in, next_tab, go_back, page_down, undo...) pass `times`. Media keys reach music and video apps without focusing them; seek_forward / seek_backward take value = seconds and act on the app in front (for a video on the assistant's own display use video_player instead). restart, shutdown and toggle_wifi put a confirmation on the user's screen and do NOT happen until they press it — never claim they are done. Volume, mute, brightness and dark mode can be reversed with the `undo` tool.

## desktop_control

Controls the DESKTOP itself: the wallpaper, and tidying the files on it. Actions: wallpaper (needs 'path') | wallpaper_url (needs 'url') | current_wallpaper | organize (needs 'mode': by_type or by_date) | clean | list | stats. For 'wallpaper', 'path' must be the real path of an existing image: copy it exactly from the tool that produced it (generate_image says where it saved), and if you do not have it, find the file with file_controller action='find' first. The change is reversible, so set it without asking first. It does ONLY those. For typing, clicking, hotkeys, screenshots or closing an application use computer_control; for opening one use open_app; for reading, moving or deleting files use file_controller. Read the status it returns: 'done' was confirmed, 'unverified' means it was requested and could not be checked - say that rather than claiming success - and 'ask' means nothing happened and the question goes to the user first.

## dev_agent

The project creation agent for brand-new standalone projects. Use mode='build' only when the user wants a NEW project created from scratch. Do NOT use this tool to modify an existing project when opencode_agent is available; use opencode_agent for fixes, features, refactoring and reviews of existing folders. mode='status' reports the progress of a build started by this tool. Jobs run in the background. Before calling build, FIRST say one short sentence that you are handing it to the coding agent, then call it in the same turn.

## edit_screen_marks

Edit one temporary annotation on the actual desktop without rebuilding the others. Use add to create a mark, update to change its properties, move to translate by dx/dy, recolor to change tone, delete to remove only one mark, or clear to remove all marks. For update/move/recolor/delete use the exact element_id from inspect_screen_marks. dx/dy are normalized whole-primary-screen units (0–1000). The operation only changes the annotation overlay; it never clicks or edits the underlying application.

## edit_visual

Edit the existing on-screen teaching board at element level. Use add to insert one element, update to change one element's properties, delete to remove only one element, and move to translate one element by dx/dy percentages. Every element has a stable element_id; use IDs from the current scene, never guess. Do not call show_visual with replace for a local edit. For a complete new scene, use show_visual operation=replace. The board remains on the primary monitor.

## file_controller

Manages and opens the user's files and folders. Actions: open (opens a folder in Windows File Explorer), list, create_file, create_folder, delete, move, copy, rename, read, write, find, largest, disk_usage, info. For common folders use the exact path shortcuts: desktop, downloads, documents, pictures, music, videos, home. On Windows, videos means the user's Videos known folder (normally C:\\Users\\<username>\\Videos), NOT C:\\Videos. Use open to show a folder visually; use list only to enumerate its contents.

## file_processor

Processes only the file currently selected or dropped into the JARVIS file box; any different local path is refused. File contents are sent to the configured Gemini model for analysis, so only select files you intend to share. Supports: images (describe/ocr/resize/compress/convert), PDFs (summarize/extract_text/ocr/to_word), Word docs & text files (summarize/fix/reformat/translate), CSV/Excel (analyze/stats/filter/sort/convert), JSON/XML (validate/format/analyze), code files (explain/review/fix/optimize/document/test; running code is blocked by default), audio (transcribe/trim/convert/info), video (trim/extract_audio/extract_frame/compress/transcribe/info), archives (list/extract), presentations (summarize/extract_text). File size, image dimensions and file signatures are validated. Generated files require HUD approval; read-only analysis does not save by default.

## flight_finder

Searches Google Flights and speaks the best options.

## focus_mode

Manage an explicit focus session. action=start begins a 5–240 minute focus block (25 minutes by default), optionally with task. While active, JARVIS checks the foreground app and window title locally every 20 seconds. After two consecutive checks on a configured distraction (video/social/game apps or sites), it gives a gentle reminder, no more often than every 3 minutes. It does not capture screenshots, read page contents, record keystrokes, block apps, or send screen data to a service. Starting another block replaces the current one. action=stop ends it; action=status reports remaining time. Use only when the user explicitly asks for focus/accountability.

## game_updater

THE ONLY tool for ANY Steam or Epic Games request. Use for: installing, downloading, updating games, listing installed games, checking download status, scheduling updates. ALWAYS call directly for any Steam/Epic/game request. NEVER use browser_control or web_search for Steam/Epic.

## highlight_screen_target

Highlight one exact control on the REAL Windows desktop with an animated, click-through teal frame and numbered caption. First inspect the screen or use an exact label already returned by screen_perception. The label must resolve to exactly one enabled UI Automation control in a fresh foreground-window scan; fuzzy matches, OCR text, guessed coordinates, and duplicate labels are refused. After speaking the current instruction, call wait_for_guidance_click to wait for the user's real left click inside that exact rectangle. Re-resolve the next target from a fresh screen view after every click. The frame never clicks for the user.

## inspect_screen_marks

Inspect the current temporary desktop annotations. Returns stable element_id values and each mark's kind, text, normalized position, size and tone. ALWAYS call this before editing a mark if you do not already know its exact ID. Does not change the screen.

## inspect_visual

Inspect the currently open teaching board and return every element's stable element_id, type, text and coordinates. ALWAYS call this before edit_visual when you do not already know the exact ID. This reads the board without changing it.

## jarvis_health

Run a local, read-only health check of JARVIS. Use scope='summary' for a short status, or scope='full' for memory integrity, task queue/checkpoints, agent profiles, Windows auto-start, configured cloud providers, local speech input and system memory. This tool never repairs, restarts, changes settings, or displays API keys, tokens, private task text, or command lines.

## open_app

Opens an application on this computer. Use whenever the user asks to open, launch or start any app or program. Put the application's name in 'app_name' exactly as the user said it. This tool answers immediately and confirms the launch in the background: on status=started say only that it is opening, never that it is open. If it does not appear, you will be told separately - relay that plainly rather than claiming success. Never say you opened something without calling this tool. To CLOSE an application use computer_control with action='close_app', not this tool. DO NOT use this tool to reach a WEB PAGE. 'open Chrome and go to YouTube', 'open YouTube', 'search the web' are all browser_control alone - it opens the browser itself. Calling open_app for the browser first and browser_control after it launches the browser TWICE, the second copy on a different profile, which is what puts a 'Who's using Chrome?' picker on the screen. Use this tool only when the user wants the application and nothing in it.

## opencode_agent

Agente especialista de programaÃƒÂ§ÃƒÂ£o para MODIFICAR ou REVISAR projetos EXISTENTES. Use para corrigir bugs, implementar funcionalidades, refatorar e testar. Informe project_dir com o caminho completo da pasta. mode='improve' implementa; mode='review' apenas analisa; mode='status' consulta o andamento. Para criar um projeto novo do zero, use dev_agent. NÃƒÂ£o use dev_agent para modificar projetos existentes quando OpenCode estiver disponÃƒÂ­vel.

## present_visual_lesson

Present an educational explanation as ordered visual beats on the real desktop. Use this by default for teaching a process, multi-step explanation, comparison or connected concepts; do not wait for the user to explicitly request a drawing. Generate the explanation, examples and visuals afresh for the actual question, including geometry. Say one short sentence naming the subject so the user hears you immediately, then call this tool in the same turn. The audio pipeline narrates your supplied captions; do not repeat them after the tool returns. Use show_visual only for one standalone diagram or a small visual addition. Always provide custom beats: there are no saved topic scenes or lesson scripts. Adapt the depth and illustration to this question and the user's follow-ups. For unfamiliar or changing facts, use the available research tools first rather than inventing facts. Each beat is {say, elements, wait?, target?, role?, timeout?, expect_text?}. say is the exact short caption that Gemini must narrate. IMPORTANT: narration always uses the currently selected Gemini Live voice. Never invoke Windows SAPI, the Windows narrator, Edge TTS, Piper or another local/system TTS voice. For an ordinary lesson with no click/hover waits, the tool stores each beat in its own visual range on one editable board and returns immediately. The board begins blank and follows your live transcription and speaker audio. Short audio segments are prepared concurrently and played in order; their actual sample counts determine stage boundaries, not character-rate estimates. Follow its result: never duplicate the prepared narration. Everything is a real-time holographic 3D scene; flat 2D elements are rejected. Each beat holds ONE model3d element in the same box (x=2, y=3, width=62, height=88), CUMULATIVE: it contains every part from earlier beats plus what this beat introduces, so the newest beat replaces the previous one and the camera and user rotation are kept. The first beat starts with a large recognizable subject body. model3d fields: shape (none or main body), parts[] (shape sphere/cube/cylinder/cone/torus/capsule/disc/pyramid/ring/plane, size, color, short label, dx/dy/dz, motion orbit/spin/pulse/bob/slide, parent, orbit_radius, tilt, node, count+arrange, opacity, glow, render_style solid/glass/hologram/glow) and links [{from,to,color,flow}] for animated flows. Abstract subjects (history, economy, code) become spatial 3D metaphors of labelled bodies. Short text/formula captions or a quiz go in the right column (x 67-98), never over the model. If PRESENTATION_INVALID is returned, fix the indicated elements and retry before speaking. Optional cue_words gives, per element, the word in say at which that element should appear. A lesson is limited to 48 visual elements total and 18 per beat. deep=true is for guided walkthroughs where one focused stage is intentionally shown at a time. For a real application walkthrough, set wait='click' or 'hover' and give target as the exact accessible label of one enabled control currently visible in the foreground Windows app. The tool highlights that real control, lets the user interact through the transparent visual overlay, and waits for a physical left click or a fresh hover held over the control. It re-reads the screen before resolving the next step. Since user interaction pauses the tool, keep captions visible; Gemini narrates after the walkthrough returns. Never guess the next target; give its exact label in that next beat. Escape or timeout pauses the lesson without claiming completion. A click is not proof that the application accepted it; provide expect_text only when a specific visible result must be verified. Speech preparation uses short sessions with the same Gemini Live model and selected voice; no extra service or local voice is used.

## reminder

Timed reminders. Default action=create with date, time and message. Use action=list to view reminder IDs and statuses; complete to mark one done and cancel its pending OS notification; reopen to restore a future notification or reopen an overdue commitment; cancel to cancel it without deleting its history. Use the exact ID returned when creating or listing a reminder.

## routines

Routines — things the assistant does on its own when a moment comes. add: kind 'say' = speak a fixed reminder (text = the exact words, in the user's language); kind 'prompt' = carry out an instruction at that moment with your tools (text = the instruction, e.g. 'tell me the weather and my agenda'); kind 'task' = start a background task (text = the task, agent researcher|general, minutes). WHEN, one of: at 'YYYY-MM-DD HH:MM' (once) | time 'HH:MM' + optional days (numbers 1=Mon…7=Sun; weekdays = [1,2,3,4,5]) | monthly_day 1-31 + time | every_minutes + optional between 'HH:MM-HH:MM' | on 'startup' | on 'idle' + idle_minutes. The built-in routines are builtin 'briefing' (the opening briefing: news_topic, extra, news true/false), 'checkin' (unprompted check-ins: focuses = what they may be about) and 'news_watch' (the watched topics' headlines). list = all routines with ids; update = change one by id or builtin (enabled, when, text, and the options above); remove = delete by id; run_now = do it now; quiet_hours = 'HH:MM-HH:MM' when unprompted routines stay silent (empty turns it off). For a one-off reminder at a date and time, the reminder tool also shows a system notification.

## screen_perception

Read the current foreground application through Windows accessibility and interact with visible controls by exact label. Use action=inspect first to see visible controls. If inspection returns SCREEN_UNAVAILABLE, do not give up: use screen_process with angle='screen' to inspect the actual screenshot, then use computer_control action='screen_find' or 'screen_click' to locate a described visual target. If JARVIS is covering the desktop, minimize only JARVIS first. Then click/double_click/right_click, type into a named edit field, press a key, scroll, or hover. Every interaction takes a fresh screen snapshot and requires one unique exact control label; never invent coordinates. Password fields are blocked. For actions that matter, provide expect_text to verify a visible postcondition. Without it, report input delivered but NOT verified.

## search_conversation_history

Search the full local archive of past JARVIS conversations by exact phrase, project, decision, person or topic. Use this whenever the user refers to a previous chat, says 'we discussed this before', asks what was decided, or expects continuity beyond the recent context already shown. Do not claim you have no memory until you search. Returns matching original user and assistant turns in chronological order. Local archive only; credentials are redacted before storage.

## search_semantic_memory

Search durable memory by meaning and related entities across personal facts, projects, tasks and session events. Use when the user refers to an older project, person, decision, blocker, task or event that is not already in context. For exact wording from an old conversation, use search_conversation_history instead. This index excludes raw conversation turns and credential-like content.

## send_message

Sends a text message via WhatsApp, Telegram, or another messaging platform. Write 'message_text' in the USER'S OWN LANGUAGE, exactly what they asked to be said. This tool answers immediately and sends in the background. On status=started say only that you are sending it, never that it is sent. The result follows separately: status=done means it was confirmed delivered to the conversation, status=unverified means the keystrokes went out and NOBODY can confirm it arrived - say exactly that - and status=failed means it did not go. Never tell the user a message was sent unless the result said status=done.

## show_screen_marks

Draw temporary visual pointers, circles, frames, arrows, checks, cross marks, underlines, highlights, labels or a spotlight over the REAL desktop on the PRIMARY monitor. Use this after screen_process has provided a fresh screenshot or the user selected a screen area. Coordinates x,y,w,h and path points use a 0–1000 grid over the captured primary-screen image (0,0 top-left; 1000,1000 bottom-right). For a box, x,y are its centre. For line/curve/trace/arrow/connect provide points [[x,y],...]. Use target/ring/frame/highlight to indicate a control or region; use label/write to write beside it. These marks are temporary and disappear after duration seconds. This does not click or alter the target application; it only draws annotations.

## show_visual

Show ONE real-time holographic 3D scene on the primary monitor. Every explanation is 3D; flat 2D elements (line, arrow, circle, rect, polygon, curve, table, graph, timeline, mindmap, map, molecule) are rejected. Provide a title and one model3d element (x=2, y=3, width=62, height=88) that holds the whole scene: shape (none or a main body), parts[] (shape sphere/cube/cylinder/cone/torus/capsule/disc/pyramid/ring/plane, size, color, short label, dx/dy/dz, motion orbit/spin/pulse/bob/slide, parent, orbit_radius, tilt, node, count+arrange, opacity, glow, render_style solid/glass/hologram/glow) and links [{from,to,color,flow}] for animated flows. Abstract subjects become spatial 3D metaphors of labelled bodies. Optional short text/formula captions or a quiz go in the right column (x 67-98), never over the model. DEFAULT operation is append: it keeps the current board; use replace only when the user asks to start over. For follow-up edits use inspect_visual then edit_visual. The user can drag the model to rotate it. For a multi-stage explanation use present_visual_lesson.

## use_skill

Load the full instructions for one installed specialized skill. Use this BEFORE carrying out a task when it matches a skill listed in the system prompt (for example pdf, docx, xlsx, pptx, frontend-design, mcp-builder, skill-creator). Pass the exact skill slug. Returns its SKILL.md and the path to supporting resources. This reads instructions; it does not automatically execute scripts or install dependencies.

## video_player

Puts a VIDEO or a PICTURE on the assistant's own display, where the avatar normally is - and closes it, mutes it or unmutes it. Use it whenever the user wants to watch or look at something on screen, whatever words or language they use for it. 'source' accepts the full path of a file on this computer, a direct video URL, a YouTube link, or a description to search YouTube for. For a file, copy its path exactly from the tool that produced it; if you do not have the path, find the file with file_controller action='find' first - never invent one. Pictures (including one generate_image just made) are shown; videos play. Set 'source_type' from what the user MEANT: 'file' when it is something on their own computer, 'web' when they mean YouTube or something online, 'auto' when they did not say. Video always starts MUTED - only call action='unmute' when the user actually asks to hear it. action='stop' closes a picture as well. While a video is on the display: 'forward' / 'back' with seconds ('skip 30 seconds' -> forward, seconds=30; no amount = 10), 'seek_to' with position ('go to 1:20' -> position='1:20'), 'pause', 'resume'. When it answers 'status=opening', say in one short sentence that you are putting it on the display, and do not wait or call it again. If it fails, report why; never open a browser instead unless the user asks for that. Do NOT use 'youtube_video' for this: that plugin works in the web browser and never shows anything on this display.

## wait_for_guidance_click

Wait for the user's next physical interaction inside the exact highlighted control. Call only after highlight_screen_target has displayed a fresh, unique Windows UIA target and you have spoken the instruction. mode=click (default) waits for a new physical left click; mode=hover waits for a fresh pointer entry held over the target for 0.45 seconds without a mouse button pressed. Escape or timeout pauses the step. The tool never clicks automatically and never treats a mark as input. A click is not proof the app accepted it; supply expect_text only when a visible postcondition must be verified. A hover is only an observed pointer interaction; inspect the changed screen before selecting the next target.

## weather_report

Gives the weather report to user

## web_search

Searches the web. Use for ANY question about current facts, events, prices, or topics — always prefer this over guessing. For news requests, use mode='news'; for a general news briefing use query='notícias do Brasil e do mundo hoje' (Brazilian Portuguese sources). After receiving news results, DO NOT speak only the first headline: deliver a spoken briefing covering 4-5 of the most important distinct stories, including Brazil and the world when both are represented. For each story, say what happened and why it matters in one or two natural sentences. If fewer than four articles are available, cover all useful articles. Do not read URLs or mechanically recite the raw search output. If the search returns no articles or fails, say so clearly instead of promising to search and going silent. Modes: 'search' (default), 'news' (latest headlines on a topic), 'research' (deep comprehensive answer), 'price' (product cost lookup), 'compare' (side-by-side comparison of items).

## youtube_video

Controls YouTube. Use for: playing videos, summarizing a video's content, getting video info, or showing trending videos.

## Internal live-session controls

In addition to the 41 self-describing action modules, the live conversation
runtime contains internal operations for screen capture, camera closure,
saving memory, monitor management, safe shutdown, and system status.
These are wired to the active Gemini Live session rather than separate
files in actions/.

## User-facing modules and integrations

- Holographic desktop: avatar, visual HUD, settings workspace, audio
  controls, provider selection, memory controls, plugin settings and
  identity customization.
- Built-in browser QA: Playwright-based project checks, responsive screenshots, console/request diagnostics, local-only server binding and evidence reports via tools/jarvis_browser_qa.py and core/browser_qa.py.
- JARVIS Agent workbench: a separate local web/desktop interface for
  coding tasks, plans, file changes, approvals, Codex App Server and
  workspace-oriented execution. See _jarvis_agent_ui/.
- Remote dashboard: local HTTPS dashboard with pairing and encrypted
  command transport. Requires network access and a private pairing code.
- Cloud reminders: optional Cloudflare Worker + D1 connector for syncing
  reminders with Apple Reminders/CalDAV. Requires the user's own account,
  database and secrets.
- Provider pipeline: optional alternate speech, language-model and
  text-to-speech providers; install and configure each provider separately.
- Skills: dynamically discovered playbooks loaded on demand. See SKILLS.md.

## Capability boundaries

- Main voice conversation uses Gemini Live and needs a valid personal key.
- Chess tools require a separately installed Stockfish engine.
- Wake-word activation is opt-in and requires local model/runtime downloads.
- Browser automation requires Playwright browsers.
- Some desktop automation functions are Windows-specific.
- External services require their own accounts, permissions and credentials.

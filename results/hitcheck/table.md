# Dell hit-check result table

result lines: 344; jobs in package: 344; jobs without a result: 0

### Batch A: enabled rules (plugins whose current-code hit was sampled)

| rule | n | works | broken | unsure | defect direct | executed only | static only | none | direct rate |
|---|---|---|---|---|---|---|---|---|---|
| USB-HC01 | 20 | 18 | 0 | 2 | 20 | 0 | 0 | 0 | 20/20 |
| USB-HC02 | 20 | 16 | 0 | 4 | 0 | 1 | 0 | 19 | 0/20 |
| USB-HC04 | 20 | 15 | 0 | 5 | 1 | 2 | 0 | 17 | 1/20 |
| USB-HC05 | 19 | 16 | 0 | 3 | 0 | 0 | 0 | 19 | 0/19 |
| USB-HC08 | 20 | 16 | 0 | 4 | 3 | 0 | 0 | 17 | 3/20 |
| USB-HC09 | 20 | 17 | 0 | 3 | 0 | 0 | 0 | 20 | 0/20 |
| USB-HC10 | 20 | 17 | 0 | 3 | 2 | 0 | 0 | 18 | 2/20 |
| USB-HC15 | 20 | 16 | 0 | 4 | 2 | 1 | 0 | 17 | 2/20 |
| USB-HC16 | 20 | 15 | 1 | 4 | 0 | 0 | 20 | 0 | 0/20 |
| USB-HC17 | 20 | 17 | 0 | 3 | 0 | 0 | 0 | 20 | 0/20 |
| USB-HC19 | 20 | 13 | 0 | 7 | 0 | 2 | 0 | 18 | 0/20 |
| USB-HC20 | 20 | 17 | 0 | 3 | 0 | 8 | 0 | 12 | 0/20 |
| USB-HC25 | 20 | 13 | 1 | 6 | 0 | 4 | 0 | 16 | 0/20 |
| USB-L02 | 7 | 6 | 0 | 1 | 0 | 7 | 0 | 0 | 0/7 |
| USB-L03 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 1/1 |
| USB-N01 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 0/2 |
| USB-N02 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 1/1 |

### Batch A: skip-rule cases (old rule fired, v3-fixes skip conditions suppress it; 'direct' would mean the skip hid a real defect)

| rule | n | works | broken | unsure | defect direct | executed only | static only | none | direct rate |
|---|---|---|---|---|---|---|---|---|---|
| USB-HC01 | 6 | 4 | 0 | 2 | 6 | 0 | 0 | 0 | 6/6 |
| USB-HC02 | 6 | 5 | 0 | 1 | 0 | 0 | 0 | 6 | 0/6 |
| USB-HC05 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 0/2 |
| USB-HC06 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 7 | 0/7 |
| USB-HC08 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0/1 |
| USB-HC13 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0/1 |
| USB-HC15 | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0/1 |
| USB-HC17 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0/1 |
| USB-HC18 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 6 | 0/6 |
| USB-HC24 | 6 | 6 | 0 | 0 | 0 | 1 | 0 | 5 | 0/6 |

### Batch A: clean controls (should load and show no defect)

| job | verdict | error |
|---|---|---|
| a-syn.ok.overlay-open-close | works |  |
| a-syn.ok.panel-open-close | works |  |
| a-syn.ok.bash-c-shellquote | works |  |
| a-syn.ok.mktemp-guarded-cleanup | works |  |

### Batch A: broken plugins in rule samples (first error)

| rule | plugin job | error |
|---|---|---|
| USB-HC16 | a-pixygon__micromachee | qml-fatal:  widget io.pixygon.micromachee failed: file:~/.config/omarchy/plugins/io.pixygon.micromachee/Panel.qml:957:17: Unexpected token `identifier |
| USB-HC25 | a-whiteovis__light | qml-fatal:  qml: Unable to create shared Light panel: file:~/.config/omarchy/plugins/light.bible-reader/Panel.qml:1442:11: Type RadioPlayer unavailabl |
| USB-N02 | a-syn.manifest.no-schema-version | plugin not listed/registered by the shell |
| USB-L03 | a-syn.qml.required-injected-property | qml-fatal: WARN scene: file:~/.config/omarchy/plugins/sample.net-badge/BarWidget.qml[7:3]: Required property shell was not initialized |

### Batch B: version-history pairs

| pair | bug kind | file | pre-fix broken? | pre-fix differs? | pre verdict | post verdict | post-fix works? | confirmed | evidence |
|---|---|---|---|---|---|---|---|---|---|
| b01-meviusisback__keybinds-plugin | syntax-or-parse-error | KeybindsPanel.qml | yes | yes | broken | works | yes | YES | qml-fatal: WARN scene: file:~/.config/omarchy/plugins/meviusisback.keybinds/KeybindsPanel.qml[874:21]: Unexpec |
| b02-vex-7k9__vex-system-monitor | syntax-or-parse-error | StatsService.qml | no | yes | works | works | yes | YES | process set differs |
| b03-mtolhuys__omarchy-news-radar | syntax-or-parse-error | src/Panel.qml | no | yes | works | works | yes | YES | process set differs |
| b04-mahziyarng98__jalali-calendar | api-compat-change | Panel.qml | no | yes | works | works | yes | YES | WARN scene: file:~/.config/omarchy/plugins/io.github.mahziyarng98.jalali-calendar/Panel.qml[174:-1]: |
| b05-koyphish__omarchy-audio-visualizer | api-compat-change | BarWidget.qml | no | yes | works | works | yes | YES | ipc io.github.koyphish.audio-visualizer.show |
| b06-davedes83__fossfetch | api-compat-change | Panel.qml | no | yes | works | works | yes | YES | WARN scene: file:~/.config/omarchy/plugins/davedes.fossfetch/Panel.qml: Unable to assign [undefined] |
| b07-silvaio__emoji-access | api-compat-change | EmojiAccess.qml | no | yes | works | works | yes | YES | WARN scene: file:~/.config/omarchy/plugins/silvaio.emoji-access/EmojiAccess.qml[357:-1]: TypeError:  |
| b08-sh1d0w__omatrack | api-compat-change | views/EntriesView.qml | no | yes | works | works | yes | YES | process set differs |
| b09-omacheese__omastorm-nord | null-or-missing-guard | ui/RadarMap.qml | no | yes | works | works | yes | YES | process set differs |
| b10-itsvoid-tv__omarchy-chroma | null-or-missing-guard | ui/ControlView.qml | no | yes | works | works | yes | YES | ipc io.github.itsvoid-tv.command-chroma.show |
| b11-devgtv__omarchy-docker | null-or-missing-guard | Panel.qml | no | yes | works | works | yes | YES | ipc devgtv.docker.show |
| b12-knivfjell__omarchy-super-button | wrong-path-or-command | RemoteSeatPad.qml | no | yes | works | works | yes | YES | process set differs |
| b13-sudoapwh__omarchy-protonvpn | wrong-path-or-command | Service.qml | no | yes | works | works | yes | YES | ipc omarchy-protonvpn.show |
| b14-szaidi-code__quran-plugin | wrong-path-or-command | BarWidget.qml | no | yes | works | works | yes | YES | process set differs |
| b15-ekollof__omaconnect | error-handling | Kcd.qml | no | yes | works | works | yes | YES | WARN scene: file:~/.config/omarchy/plugins/ekollof.omaconnect/Kcd.qml[523:-1]: Error: Cannot assign  |
| b16-guiestrela__weather | error-handling | Panel.qml | no | yes | works | works | yes | YES | ipc io.github.guiestrela.weather.show |
| b17-ferc10110__omarchy-runbook | error-handling | Panel.qml | no | yes | works | works | yes | YES | ipc io.github.ferc10110.runbook.show |
| b18-dawestheperson__hyperwyrm | process-or-resource-lifecycle | src/EvolveScene.qml | no | yes | works | works | yes | YES | ipc dawestheperson.hyperwyrm.show |
| b19-davedes83__omarchy-netspeed-plugin | process-or-resource-lifecycle | BarWidget.qml | no | yes | works | works | yes | YES | process set differs |
| b20-znow01__veilleuse | process-or-resource-lifecycle | Panel.qml | no | yes | works | works | yes | YES | process set differs |
| b21-murankar__omarchy-eso-server-status | env-or-config-assumption | BarWidget.qml | no | yes | works | works | yes | YES | process set differs |
| b22-kristijan-k__omarchy-youtube-suggester | env-or-config-assumption | BarWidget.qml | no | yes | works | works | yes | YES | process set differs |
| b23-tiagovello__paper-cast | race-or-timing | Panel.qml | no | yes | works | works | yes | YES | process set differs |
| b24-alanfortlink__clipboard-history | race-or-timing | PreviewPane.qml | no | yes | works | works | yes | YES | process set differs |
| b25-nixfred__pastey | missing-dependency-or-install | Panel.qml | no | yes | works | works | yes | YES | ipc nixfred.pastey.show |
| b26-gdeyoung__omarchy-sysmon | ui-layout-or-state | DetailPopup.qml | no | yes | works | works | yes | YES | ipc gdeyoung.sysmon.status |
| b27-harbefas__omarchy-almanac | ui-layout-or-state | ManagerPanel.qml | no | yes | works | works | yes | YES | ipc harbefas.almanac.show |
| b28-mlambert-uk__omarchy-govee | wrong-condition-or-logic | Panel.qml | no | yes | works | works | yes | YES | ipc mlambert-uk.govee.show |
| b29-herman6888__newswire-omarchy | wrong-condition-or-logic | NewsPopup.qml | yes | yes | broken | broken | no | no | qml-fatal: Plugin widget herman.newswire-zh failed: file:~/.config/omarchy/plugins/herman.newswire-zh/Widget.q |
| b30-petealeon__dailybiblereadings | security | BarWidget.qml | no | yes | works | works | yes | YES | ipc petealeon.dailybiblereadings.show |

### Batch B: totals

| pairs | pre-fix broken | pre-fix differs | pre broken and post works | post-fix works | confirmed |
|---|---|---|---|---|---|
| 30 | 2 | 30 | 1 | 29 | 29 |

### Batch B: by bug kind

| bug kind | pairs | pre-fix broken | pre-fix differs | post-fix works | confirmed |
|---|---|---|---|---|---|
| api-compat-change | 5 | 0 | 5 | 5 | 5 |
| env-or-config-assumption | 2 | 0 | 2 | 2 | 2 |
| error-handling | 3 | 0 | 3 | 3 | 3 |
| missing-dependency-or-install | 1 | 0 | 1 | 1 | 1 |
| null-or-missing-guard | 3 | 0 | 3 | 3 | 3 |
| process-or-resource-lifecycle | 3 | 0 | 3 | 3 | 3 |
| race-or-timing | 2 | 0 | 2 | 2 | 2 |
| security | 1 | 0 | 1 | 1 | 1 |
| syntax-or-parse-error | 3 | 1 | 3 | 3 | 3 |
| ui-layout-or-state | 2 | 0 | 2 | 2 | 2 |
| wrong-condition-or-logic | 2 | 1 | 2 | 1 | 1 |
| wrong-path-or-command | 3 | 0 | 3 | 3 | 3 |

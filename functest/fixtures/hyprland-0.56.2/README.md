Hyprland 0.56.2 `hyprctl` reply shapes for the functest's hyprctl emulator (`functest/dell_env/hyprctl.py`).
- `options_raw.json`: every config option name -> [type, default] parsed from hyprwm/Hyprland v0.56.2
  (efb50993780079460b0cbed1363e2166a2de1d9f) `src/config/values/ConfigValues.cpp`. getoption JSON keys per type follow
  `src/debug/HyprCtl.cpp` dispatchGetOption (Int/Color->int, Bool->bool, Float->float, String->str, CssGap->css,
  Gradient->gradient, Vec2->vec2, FontWeight->font_weight). CssGap is `css`, not `custom`/`int`.
- `fixtures.json`: monitors/clients/workspaces/devices/layers/binds/version JSON with the exact key sets of HyprCtl.cpp at that tag.
  Values are **sanitised**: monitor make/model, input device names and window class/title are generic placeholders. The original
  raw device capture is not published.
Hyprland is BSD-3-Clause (Copyright (c) 2022-2026, vaxerski); only output formats are reproduced here.

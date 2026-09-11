# 程序图标

使用内置 image_gen 生成，原图保存在 `app-icon.png`。
`app-icon.ico` 从原图转换，包含 16、20、24、32、40、48、64、128、256 像素尺寸，用于窗口及 EXE。

使用 `uv run python tools/build_icon.py` 重新生成图标。ICO 使用 32 位 RGBA 的 DIB 编码，避免 Tk 将 PNG 图标条目统一缩放后选中放大的小图。更换图标后使用 `uv run pyinstaller --noconfirm --clean main_fast.spec` 打包，确保 EXE 图标资源更新。

## 生成提示词

```text
Use case: style-transfer
Asset type: final square Windows program icon.
Edit target: the attached current application icon.
Primary request: revise the icon to depict Shoko Komi (Komi Shouko / 古见硝子) from the anime Komi Can't Communicate much more faithfully, using her recognizable original anime character design instead of a generic pretty anime girl.
Character corrections: slender elegant face with a small pointed chin; long straight nearly black hair, flat dark violet shadow shapes, Komi's characteristic long pointed central fringe and neat side locks; her distinctive elongated almond-shaped eyes with dark upper lashes and dark purple irises, slightly wide and quietly attentive; tiny simple nose and tiny closed mouth, reserved neutral expression, almost no blush. Classic anime Komi, not the round-faced glossy mobile-game illustration. Show the top of her navy school blazer, white shirt collar and small burgundy ribbon, entirely modest and non-sexual.
Visual corrections: remove the ENTIRE glowing violet perimeter, remove any border stroke, rim light, halo, glitter, petals, dots, orbit lines, gradients and special effects. Replace the background with one absolutely flat very pale cool gray rounded square, transparent only outside its corners. Clean smooth edges. NO PURPLE GLOW ANYWHERE.
Style: faithful simple 2D TV anime cel animation, restrained flat palette, clean dark outlines, one or two solid shadow tones, no painterly rendering, no shiny skin, no elaborate hair highlights.
Preserve: single centered head-and-shoulders portrait as an application icon, large readable face, square composition, no text, no watermark, no props.
Result: understated, clean, immediately recognizable as Komi Shouko.
```

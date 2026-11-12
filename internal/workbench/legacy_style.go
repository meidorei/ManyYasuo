package workbench

import "github.com/egoist/mygo/ui"

// Warm ceramic surfaces share a top-left light source. Keep native MyGo
// controls so keyboard input, focus and disabled semantics remain intact.
var (
	legacySurface       = ui.RGB(244, 241, 234)
	legacyShadow        = ui.RGB(212, 202, 190)
	legacyLight         = ui.RGB(255, 252, 247)
	legacyControlBorder = ui.RGB(139, 127, 112)
	softDivider         = ui.RGB(221, 213, 201)
	softHover           = ui.RGB(248, 237, 224)
	softText            = ui.RGB(54, 49, 43)
	softMuted           = ui.RGB(112, 103, 92)
	softAccent          = ui.RGB(185, 79, 16)
	softAccentHover     = ui.RGB(169, 71, 14)
	softAccentPressed   = ui.RGB(148, 59, 10)
	softAccentText      = ui.RGB(159, 65, 13)
)

func raised(e ui.Element, radius float32) ui.Element {
	return e.NoShadow().Background(legacySurface).Radius(radius).
		Shadow(-2, -2, 5, 0, legacyLight).Shadow(2, 2, 5, 0, legacyShadow)
}
func recessed(e ui.Element, radius float32) ui.Element {
	return e.NoShadow().Background(legacySurface).Radius(radius).
		InsetShadow(2, 2, 4, 0, legacyShadow).InsetShadow(-2, -2, 4, 0, legacyLight)
}
func action(c *ui.Context, label string) ui.Element {
	b := ui.Button(c, label).Height(36).BorderWidth(0).FontSize(13).FocusRingOffset(2)
	if b.Pressed() {
		return recessed(b, 10)
	}
	b = raised(b, 10)
	if b.Hovered() {
		b.Background(softHover)
	}
	return b
}
func primaryAction(c *ui.Context, label string, disabled bool) ui.Element {
	b := action(c, label).Disabled(disabled).Bold().FontSize(15).NoShadow()
	if disabled {
		return raised(b, 10).TextColor(softMuted)
	}
	if b.Pressed() {
		return b.Gradient(softAccentPressed, softAccentHover, 135).
			InsetShadow(3, 3, 6, 0, ui.RGBA(85, 31, 4, .5)).
			InsetShadow(-2, -2, 5, 0, ui.RGBA(255, 220, 180, .25)).
			TextColor(ui.RGB(255, 255, 255))
	}
	face, shade := softAccent, softAccentHover
	if b.Hovered() {
		face, shade = softAccentHover, softAccentPressed
	}
	return b.Gradient(face, shade, 135).
		Shadow(-4, -4, 9, 0, legacyLight).Shadow(4, 4, 9, 0, ui.RGB(195, 177, 155)).
		InsetShadow(1, 1, 2, 0, ui.RGBA(255, 238, 214, .3)).
		InsetShadow(-1, -1, 2, 0, ui.RGBA(104, 38, 4, .25)).
		TextColor(ui.RGB(255, 255, 255))
}
func quietAction(c *ui.Context, label string) ui.Element {
	b := action(c, label).TextColor(softMuted)
	if !b.Hovered() && !b.Pressed() {
		b.NoShadow()
	}
	return b
}
func card(c *ui.Context) ui.Element {
	return ui.Column(c).Background(legacySurface).Radius(16).MinWidth(0).
		Shadow(-4, -4, 12, 0, legacyLight).Shadow(4, 4, 12, 0, legacyShadow)
}
func input(c *ui.Context, label string, value *string, locked bool, changed func()) ui.Element {
	e := recessed(ui.TextInput(c, value).Label(label).Height(36).Disabled(locked).OnChange(changed), 10).
		BorderWidth(0).FocusRingOffset(2)
	return e.FocusRing(e.Focused())
}
func smallLabel(c *ui.Context, text string) ui.Element {
	return ui.Text(c, text).FontSize(12)
}

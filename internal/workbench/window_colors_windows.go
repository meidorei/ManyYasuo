package workbench

import (
	"fmt"
	"runtime"
	"syscall"
	"unsafe"

	"github.com/egoist/mygo/ui"
)

const (
	dwmCaptionColor = 35
	dwmTextColor    = 36
)

var dwmSetWindowAttribute = syscall.NewLazyDLL("dwmapi.dll").NewProc("DwmSetWindowAttribute")

// setNativeWindowColors runs on the window's UI thread. DWM caption colors
// require Windows 11; failure leaves the native system title bar in place.
// COLORREF is 0x00BBGGRR, unlike a CSS hex color or an ARGB pixel.
func setNativeWindowColors(hwnd uintptr, background, text ui.Color) error {
	if err := dwmSetWindowAttribute.Find(); err != nil {
		return err
	}
	for _, attribute := range []struct {
		id    uintptr
		color ui.Color
	}{{dwmCaptionColor, background}, {dwmTextColor, text}} {
		value := windowColorRef(attribute.color)
		hr, _, _ := dwmSetWindowAttribute.Call(hwnd, attribute.id, uintptr(unsafe.Pointer(&value)), unsafe.Sizeof(value))
		runtime.KeepAlive(&value)
		if int32(hr) < 0 {
			return fmt.Errorf("DWM attribute %d: %w", attribute.id, syscall.Errno(uint32(hr)))
		}
	}
	return nil
}

func windowColorRef(c ui.Color) uint32 {
	return uint32(c.R) | uint32(c.G)<<8 | uint32(c.B)<<16
}

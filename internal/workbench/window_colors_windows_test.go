package workbench

import (
	"errors"
	"runtime"
	"syscall"
	"testing"
	"unsafe"
)

func TestNativeCaptionColorsPreserveWindowFrame(t *testing.T) {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	user32 := syscall.NewLazyDLL("user32.dll")
	class, err := syscall.UTF16PtrFromString("STATIC")
	if err != nil {
		t.Fatal(err)
	}
	// A real hidden top-level window: no WS_VISIBLE, no focus stealing, no
	// application files or configuration involved in this DWM integration test.
	const overlappedWindow = 0x00CF0000
	hwnd, _, createErr := user32.NewProc("CreateWindowExW").Call(0,
		uintptr(unsafe.Pointer(class)), 0, overlappedWindow, 0, 0, 320, 200, 0, 0, 0, 0)
	runtime.KeepAlive(class)
	if hwnd == 0 {
		t.Fatal("create hidden native window:", createErr)
	}
	defer user32.NewProc("DestroyWindow").Call(hwnd)
	// These attributes are set-only in the documented DWM API. Validate the
	// native setter's HRESULT, not an unsupported DwmGetWindowAttribute query.
	if err := setNativeWindowColors(hwnd, legacySurface, softText); err != nil {
		if errors.Is(err, syscall.Errno(0x80070057)) {
			t.Skip("DWM caption colors require Windows 11; this OS keeps the system title bar")
		}
		t.Fatal(err)
	}
	styleIndex := int32(-16) // GWL_STYLE
	style, _, _ := user32.NewProc("GetWindowLongW").Call(hwnd, uintptr(styleIndex))
	if uint32(style)&overlappedWindow != overlappedWindow {
		t.Errorf("native caption, sizing border or window controls were removed: 0x%08x", uint32(style))
	}
	visible, _, _ := user32.NewProc("IsWindowVisible").Call(hwnd)
	if visible != 0 {
		t.Fatal("setting caption colors unexpectedly showed the hidden window")
	}
}

func TestNativeWindowColorEncoding(t *testing.T) {
	if got := windowColorRef(legacySurface); got != 0x00EAF1F4 {
		t.Fatalf("cream caption COLORREF = 0x%08x, want 0x00EAF1F4", got)
	}
	if got := windowColorRef(softText); got != 0x002B3136 {
		t.Fatalf("caption text COLORREF = 0x%08x, want 0x002B3136", got)
	}
}

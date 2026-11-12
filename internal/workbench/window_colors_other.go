//go:build !windows

package workbench

import "github.com/egoist/mygo/ui"

func setNativeWindowColors(hwnd uintptr, background, text ui.Color) error { return nil }

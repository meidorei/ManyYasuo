package main

import (
	"debug/buildinfo"
	"debug/pe"
	"os"
	"path/filepath"
	"testing"
)

func TestResourcesPreserveGoBuildInfo(t *testing.T) {
	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	originalInfo, err := buildinfo.ReadFile(self)
	if err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(self)
	if err != nil {
		t.Fatal(err)
	}
	target := filepath.Join(t.TempDir(), "fixture.exe")
	if err = os.WriteFile(target, data, 0755); err != nil {
		t.Fatal(err)
	}
	if err = run(target, filepath.Join("..", "..", "assets", "app-icon.ico")); err != nil {
		t.Fatal(err)
	}
	info, err := buildinfo.ReadFile(target)
	if err != nil || info.GoVersion != originalInfo.GoVersion {
		t.Fatalf("build information damaged: %v", err)
	}
	f, err := pe.Open(target)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if f.OptionalHeader.(*pe.OptionalHeader64).DataDirectory[2].VirtualAddress == 0 {
		t.Fatal("resource directory missing")
	}
}

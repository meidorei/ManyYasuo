package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDefaultsAndIndependentPersistence(t *testing.T) {
	s := &Store{Path: filepath.Join(t.TempDir(), "config.json")}
	d, err := s.Load()
	if err != nil || d.Compression.TagPrefix != "AAA_" {
		t.Fatal(d, err)
	}
	d.Preprocessing.TagPrefix = "ONLY_"
	if err = s.Save(d); err != nil {
		t.Fatal(err)
	}
	got, err := s.Load()
	if err != nil || got.Preprocessing.TagPrefix != "ONLY_" || got.Renaming.TagPrefix != "AAA_" {
		t.Fatal(got, err)
	}
}
func TestExistingPythonConfigAndMalformedConfig(t *testing.T) {
	s := &Store{Path: filepath.Join(t.TempDir(), "config.json")}
	if err := os.WriteFile(s.Path, []byte(`{"compression":{"lvl":"7-最大","pwd":"test-secret","hide_name":false},"renaming":{"tag_prefix":"XYZ_"}}`), 0600); err != nil {
		t.Fatal(err)
	}
	d, err := s.Load()
	if err != nil || d.Compression.Password != "test-secret" || d.Compression.HideName || d.Extraction.TagPrefix != "AAA_" || d.Renaming.TagPrefix != "XYZ_" {
		t.Fatal("compatibility", err)
	}
	_ = os.WriteFile(s.Path, []byte("invalid"), 0600)
	d, err = s.Load()
	if err == nil || d != Defaults() {
		t.Fatal("invalid defaults")
	}
}

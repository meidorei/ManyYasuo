package config

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

type Compression struct {
	SevenZip   string `json:"7z_path"`
	Prefix     string `json:"prefix"`
	TagPrefix  string `json:"tag_prefix"`
	Extension  string `json:"extension"`
	Level      string `json:"lvl"`
	Dictionary string `json:"dict"`
	Word       string `json:"word"`
	Solid      string `json:"solid"`
	Threads    string `json:"threads"`
	Password   string `json:"pwd"`
	HideName   bool   `json:"hide_name"`
}
type Preprocessing struct {
	Prefix    string `json:"prefix"`
	TagPrefix string `json:"tag_prefix"`
}
type Extraction struct {
	SevenZip   string `json:"7z_path"`
	Password   string `json:"password"`
	TagPrefix  string `json:"tag_prefix"`
	BlockTerms string `json:"block_terms"`
	OutputDir  string `json:"output_dir"`
}
type Renaming struct {
	TagPrefix  string `json:"tag_prefix"`
	BlockTerms string `json:"block_terms"`
}
type Settings struct {
	Compression   Compression   `json:"compression"`
	Preprocessing Preprocessing `json:"preprocessing"`
	Extraction    Extraction    `json:"extraction"`
	Renaming      Renaming      `json:"renaming"`
}

func Defaults() Settings {
	return Settings{
		Compression:   Compression{Prefix: "HGLIST-", TagPrefix: "AAA_", Extension: ".1", Level: "5-标准", Dictionary: "64 MB", Word: "64", Solid: "16 GB", Threads: "自动", HideName: true},
		Preprocessing: Preprocessing{Prefix: "HGLIST-", TagPrefix: "AAA_"},
		Extraction:    Extraction{TagPrefix: "AAA_", BlockTerms: "路径, 中文"},
		Renaming:      Renaming{TagPrefix: "AAA_", BlockTerms: "路径, 中文"},
	}
}

type Store struct {
	Path string
	mu   sync.Mutex
}

func (s *Store) Load() (Settings, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	d := Defaults()
	b, err := os.ReadFile(s.Path)
	if os.IsNotExist(err) {
		return d, nil
	}
	if err != nil {
		return d, err
	}
	var sections map[string]json.RawMessage
	if err = json.Unmarshal(b, &sections); err != nil {
		return d, fmt.Errorf("配置无法解析，使用默认值：%w", err)
	}
	// Decode sections independently so a malformed section cannot damage others.
	var warning error
	for name, dst := range map[string]any{"compression": &d.Compression, "preprocessing": &d.Preprocessing, "extraction": &d.Extraction, "renaming": &d.Renaming} {
		if raw, ok := sections[name]; ok {
			if err = json.Unmarshal(raw, dst); err != nil {
				warning = fmt.Errorf("配置分区 %s 包含无效字段：%w", name, err)
			}
		}
	}
	return d, warning
}
func (s *Store) Save(d Settings) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	b, err := json.MarshalIndent(d, "", "  ")
	if err != nil {
		return err
	}
	if err = os.MkdirAll(filepath.Dir(s.Path), 0755); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(s.Path), ".config-*.tmp")
	if err != nil {
		return err
	}
	name := f.Name()
	defer os.Remove(name)
	if _, err = f.Write(b); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(name, s.Path)
}
func DefaultPath(production bool) string {
	if !production {
		if wd, err := os.Getwd(); err == nil {
			return filepath.Join(wd, "config.json")
		}
	}
	exe, err := os.Executable()
	if err != nil {
		return "config.json"
	}
	return filepath.Join(filepath.Dir(exe), "config.json")
}

package core

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func FindMarker(root, prefix string) string {
	prefix = MarkerText(prefix)
	if prefix == "" || IsReparse(root) {
		return ""
	}
	parents := []string{root}
	for len(parents) > 0 {
		var next, matches []string
		for _, p := range parents {
			entries, err := os.ReadDir(p)
			if err != nil {
				continue
			}
			for _, e := range entries {
				path := filepath.Join(p, e.Name())
				if !e.IsDir() || IsReparse(path) {
					continue
				}
				if strings.HasPrefix(e.Name(), prefix) && len(e.Name()) > len(prefix) {
					matches = append(matches, path)
				} else {
					next = append(next, path)
				}
			}
		}
		if len(matches) > 0 {
			sort.Slice(matches, func(i, j int) bool {
				a, b := strings.ToLower(filepath.Base(matches[i])), strings.ToLower(filepath.Base(matches[j]))
				if a != b {
					return a < b
				}
				return PathKey(matches[i]) < PathKey(matches[j])
			})
			return matches[0]
		}
		parents = next
	}
	return ""
}
func MarkerTag(path, prefix string) string {
	if path == "" {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(filepath.Base(path), MarkerText(prefix)))
}
func CreateMarker(root, prefix, tag string) (string, error) {
	tag = MarkerText(tag)
	if tag == "" {
		return "", nil
	}
	p := filepath.Join(root, MarkerText(prefix)+tag)
	if Exists(p) {
		if IsReparse(p) {
			return "", fmt.Errorf("标签路径是链接：%s", p)
		}
		st, e := os.Stat(p)
		if e != nil {
			return "", e
		}
		if !st.IsDir() {
			return "", fmt.Errorf("标签路径不是目录：%s", p)
		}
		return p, nil
	}
	return p, os.Mkdir(p, 0755)
}
func RemoveEmptyMarker(root, prefix, tag string) error {
	if MarkerText(tag) == "" {
		return nil
	}
	p := filepath.Join(root, MarkerText(prefix)+MarkerText(tag))
	return removeEmptyDir(p)
}
func removeEmptyDir(p string) error {
	info, err := os.Lstat(p)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return err
	}
	if !info.IsDir() || IsReparse(p) {
		return fmt.Errorf("不能移除非普通目录：%s", p)
	}
	return os.Remove(p)
}
func BlockingFile(root string, terms []string) string {
	if len(terms) == 0 {
		return ""
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return ""
	}
	for _, e := range entries {
		p := filepath.Join(root, e.Name())
		if e.IsDir() || IsReparse(p) {
			continue
		}
		match := true
		for _, t := range terms {
			if !strings.Contains(strings.ToLower(e.Name()), t) {
				match = false
				break
			}
		}
		if match {
			return p
		}
	}
	return ""
}
func DetectTag(root, prefix string) Detection {
	base, nameTag := SplitNumberedTag(filepath.Base(root))
	markerTag := MarkerTag(FindMarker(root, prefix), prefix)
	d := Detection{PreservedName: base, NameTag: nameTag, MarkerTag: markerTag, Origin: "none"}
	if nameTag != "" && markerTag != "" && !strings.EqualFold(nameTag, markerTag) {
		d.Origin = "conflict"
	} else if markerTag != "" {
		d.Tag = markerTag
		d.Origin = "marker"
	} else if nameTag != "" {
		d.Tag = nameTag
		d.Origin = "name"
	}
	return d
}
func FolderSize(ctx context.Context, root string) (int64, error) {
	var total int64
	if IsReparse(root) {
		return 0, nil
	}
	err := filepath.WalkDir(root, func(p string, e os.DirEntry, err error) error {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if err != nil {
			return err
		}
		if IsReparse(p) {
			if e.IsDir() {
				return filepath.SkipDir
			}
			return nil
		}
		if !e.IsDir() {
			i, err := e.Info()
			if err != nil {
				return err
			}
			if i.Mode().IsRegular() {
				total += i.Size()
			}
		}
		return nil
	})
	return total, err
}
func FormatSize(size int64) string {
	if size < 0 {
		size = 0
	}
	v := float64(size)
	for i, u := range []string{"B", "KB", "MB", "GB", "TB"} {
		if v < 1024 || i == 4 {
			if i == 0 {
				return fmt.Sprintf("%d B", size)
			}
			return fmt.Sprintf("%.1f %s", v, u)
		}
		v /= 1024
	}
	return "0 B"
}

// Unwrap lifts one-child wrappers, never traversing reparse directories.
func Unwrap(root, prefix string) (int, error) {
	if IsReparse(root) {
		return 0, fmt.Errorf("不能修改链接或重解析目录：%s", root)
	}
	removed := 0
	for {
		entries, err := os.ReadDir(root)
		if err != nil {
			return removed, err
		}
		var meaningful []os.DirEntry
		for _, e := range entries {
			if e.Name() != "desktop.ini" && e.Name() != ".DS_Store" && e.Name() != "Thumbs.db" {
				meaningful = append(meaningful, e)
			}
		}
		if len(meaningful) != 1 {
			return removed, nil
		}
		e := meaningful[0]
		nested := filepath.Join(root, e.Name())
		if !e.IsDir() || IsReparse(nested) || (MarkerText(prefix) != "" && strings.HasPrefix(e.Name(), MarkerText(prefix))) {
			return removed, nil
		}
		children, err := os.ReadDir(nested)
		if err != nil {
			return removed, err
		}
		for _, ch := range children {
			if Exists(filepath.Join(root, ch.Name())) {
				return removed, fmt.Errorf("嵌套整理存在同名项目：%s", ch.Name())
			}
		}
		var moved []string
		for _, ch := range children {
			err = os.Rename(filepath.Join(nested, ch.Name()), filepath.Join(root, ch.Name()))
			if err != nil {
				break
			}
			moved = append(moved, ch.Name())
		}
		if err == nil {
			err = os.Remove(nested)
		}
		if err != nil {
			details := ""
			for i := len(moved) - 1; i >= 0; i-- {
				n := moved[i]
				if re := os.Rename(filepath.Join(root, n), filepath.Join(nested, n)); re != nil {
					details += fmt.Sprintf("；恢复失败，文件保留在 %s：%v", filepath.Join(root, n), re)
				}
			}
			return removed, fmt.Errorf("%w%s", err, details)
		}
		removed++
	}
}

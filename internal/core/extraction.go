package core

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

func ArchiveStem(path string) string {
	return strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))
}
func PreservePartial(staging, parent, stem string) string {
	entries, err := os.ReadDir(staging)
	if os.IsNotExist(err) {
		return ""
	}
	if err != nil {
		return staging
	}
	if len(entries) == 0 {
		if os.Remove(staging) == nil {
			return ""
		}
		return staging
	}
	target := UniqueDestination(parent, SanitizeName(stem)+"_解压未完成", nil)
	if os.Rename(staging, target) != nil {
		return staging
	}
	return target
}
func FinalizeExtraction(staging, parent, archive string, rules Rules) (string, string, error) {
	entries, err := os.ReadDir(staging)
	if err != nil {
		return "", "", err
	}
	payload := staging
	original := ArchiveStem(archive)
	if len(entries) == 1 && entries[0].IsDir() {
		payload = filepath.Join(staging, entries[0].Name())
		if IsReparse(payload) {
			return "", "", fmt.Errorf("解压内容包含重解析目录：%s", payload)
		}
		original = entries[0].Name()
	}
	finalName := original
	message := "已解压 · 未找到有效标签，保留原名"
	marker := FindMarker(payload, rules.TagPrefix)
	tag := MarkerTag(marker, rules.TagPrefix)
	if blocker := BlockingFile(payload, BlockTerms(rules.BlockTerms)); blocker != "" {
		message = "已解压 · 检测到“" + filepath.Base(blocker) + "”，保留原名"
	} else if tag != "" {
		base, _ := SplitNumberedTag(original)
		finalName = tag
		if base != "" {
			finalName = base + " " + tag
		}
		message = "已按标签改名为 " + SanitizeName(finalName)
	}
	target := UniqueDestination(parent, SanitizeName(finalName), nil)
	if err = os.Rename(payload, target); err != nil {
		return "", "", err
	}
	if tag != "" && strings.HasPrefix(message, "已按标签") {
		relative, _ := filepath.Rel(payload, marker)
		if e := removeEmptyDir(filepath.Join(target, relative)); e != nil {
			message += " · 标签目录已保留"
		}
	}
	if payload != staging {
		_ = os.Remove(staging)
	}
	return target, message, nil
}

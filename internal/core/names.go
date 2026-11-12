// Package core contains the filesystem rules shared by the four workspaces.
package core

import (
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

const (
	Ready        = "ready"
	Invalid      = "invalid"
	Failed       = "failed"
	Cancelled    = "cancelled"
	Done         = "done"
	Protected    = "protected"
	NoTag        = "no_tag"
	AlreadyNamed = "already_named"
)

type Rules struct{ TagPrefix, BlockTerms string }
type Preview struct{ Source, Target, Status, Message, Marker, Tag string }
type Result struct{ Source, Target, Status, Message string }
type Detection struct{ Tag, Origin, PreservedName, NameTag, MarkerTag string }

func (d Detection) Conflict() bool { return d.Origin == "conflict" }

var badName = regexp.MustCompile(`[\\/:*?"<>|\x00-\x1f]`)
var digits = regexp.MustCompile(`[0-9]+`)
var parts = regexp.MustCompile(`[0-9]+|[^0-9]+`)
var collisionSuffix = regexp.MustCompile(` \([0-9]+\)$`)
var numberedTag = regexp.MustCompile(`^(.+?[0-9]+)\s+(.+)$`)
var termSplit = regexp.MustCompile(`[,，;；\s]+`)
var reservedName = regexp.MustCompile(`(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$`)

func MarkerText(v string) string { return strings.TrimSpace(badName.ReplaceAllString(v, "_")) }
func SanitizeName(v string) string {
	v = strings.TrimRight(MarkerText(v), ".")
	if v == "" {
		v = "未命名"
	}
	if reservedName.MatchString(v) {
		v = "_" + v
	}
	r := []rune(v)
	if len(r) > 120 {
		v = string(r[:120])
	}
	return v
}
func PathKey(p string) string { a, _ := filepath.Abs(p); return strings.ToLower(filepath.Clean(a)) }
func LastNumber(s string) string {
	p := digits.FindAllString(s, -1)
	if len(p) == 0 {
		return ""
	}
	return p[len(p)-1]
}
func SplitNumberedTag(s string) (string, string) {
	s = strings.TrimSpace(collisionSuffix.ReplaceAllString(s, ""))
	m := numberedTag.FindStringSubmatch(s)
	if m != nil {
		return strings.TrimSpace(m[1]), strings.TrimSpace(m[2])
	}
	if digits.MatchString(s) {
		return s, ""
	}
	return "", ""
}
func NaturalLess(a, b string) bool {
	aa, bb := parts.FindAllString(strings.ToLower(a), -1), parts.FindAllString(strings.ToLower(b), -1)
	for i := 0; i < len(aa) && i < len(bb); i++ {
		if aa[i] == bb[i] {
			continue
		}
		x, xok := new(big.Int).SetString(aa[i], 10)
		y, yok := new(big.Int).SetString(bb[i], 10)
		if xok && yok {
			if cmp := x.Cmp(y); cmp != 0 {
				return cmp < 0
			}
			continue
		}
		return aa[i] < bb[i]
	}
	return len(aa) < len(bb)
}
func SortPaths(paths []string) {
	sort.SliceStable(paths, func(i, j int) bool {
		a, b := filepath.Base(paths[i]), filepath.Base(paths[j])
		if NaturalLess(a, b) {
			return true
		}
		if NaturalLess(b, a) {
			return false
		}
		return PathKey(paths[i]) < PathKey(paths[j])
	})
}
func Exists(p string) bool { _, err := os.Lstat(p); return err == nil || !os.IsNotExist(err) }
func UniqueDestination(parent, name string, reserved map[string]bool) string {
	p := filepath.Join(parent, name)
	for i := 2; Exists(p) || reserved[PathKey(p)]; i++ {
		p = filepath.Join(parent, fmt.Sprintf("%s (%d)", name, i))
	}
	return p
}
func SequenceTargets(sources []string, prefix, start string) ([]string, error) {
	if start == "" || strings.Trim(start, "0123456789") != "" {
		return nil, fmt.Errorf("起始编号必须是非负整数")
	}
	n, _ := new(big.Int).SetString(start, 10)
	out := make([]string, len(sources))
	for i, s := range sources {
		v := n.String()
		if len(v) < len(start) {
			v = strings.Repeat("0", len(start)-len(v)) + v
		}
		name := prefix + v
		if SanitizeName(name) != name {
			return nil, fmt.Errorf("文件名前缀包含非法字符或名称过长")
		}
		out[i] = filepath.Join(filepath.Dir(s), name)
		n.Add(n, big.NewInt(1))
	}
	return out, nil
}
func BlockTerms(s string) []string {
	var out []string
	for _, p := range termSplit.Split(strings.ToLower(s), -1) {
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

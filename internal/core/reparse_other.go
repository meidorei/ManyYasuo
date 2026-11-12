//go:build !windows

package core

import "os"

func IsReparse(path string) bool {
	info, err := os.Lstat(path)
	return err != nil || info.Mode()&os.ModeSymlink != 0
}

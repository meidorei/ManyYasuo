package core

import "syscall"

func IsReparse(path string) bool {
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return true
	}
	attrs, err := syscall.GetFileAttributes(p)
	return err != nil || attrs&syscall.FILE_ATTRIBUTE_REPARSE_POINT != 0
}

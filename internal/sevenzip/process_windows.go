package sevenzip

import (
	"fmt"
	"os"
	"os/exec"
	"syscall"
)

func configureProcess(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: 0x08000000}
}

var ntdll = syscall.NewLazyDLL("ntdll.dll")

func pauseProcess(p *os.Process, paused bool) error {
	handle, err := syscall.OpenProcess(0x0800, false, uint32(p.Pid))
	if err != nil {
		return err
	}
	defer syscall.CloseHandle(handle)
	name := "NtResumeProcess"
	if paused {
		name = "NtSuspendProcess"
	}
	fn := ntdll.NewProc(name)
	if err := fn.Find(); err != nil {
		return err
	}
	status, _, _ := fn.Call(uintptr(handle))
	if status != 0 {
		return fmt.Errorf("暂停/继续进程失败：0x%x", status)
	}
	return nil
}

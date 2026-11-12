// winresource attaches the existing ICO and a per-monitor DPI manifest to an
// executable. It uses only Windows APIs and requires no resource compiler.
package main

import (
	"bytes"
	"debug/pe"
	"encoding/binary"
	"fmt"
	"os"
	"runtime"
	"syscall"
	"unsafe"
)

const manifest = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
<assemblyIdentity version="1.0.0.0" processorArchitecture="amd64" name="ManyYasuo" type="win32"/>
<trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges></security></trustInfo>
<compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1"><application><supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/></application></compatibility>
<application xmlns="urn:schemas-microsoft-com:asm.v3"><windowsSettings><dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware><dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness><longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware></windowsSettings></application>
<dependency><dependentAssembly><assemblyIdentity type="win32" name="Microsoft.Windows.Common-Controls" version="6.0.0.0" processorArchitecture="*" publicKeyToken="6595b64144ccf1df" language="*"/></dependentAssembly></dependency>
</assembly>`

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: winresource executable icon.ico")
		os.Exit(2)
	}
	if err := run(os.Args[1], os.Args[2]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
func run(exe, icon string) error {
	original, err := os.ReadFile(exe)
	if err != nil {
		return err
	}
	coff, err := pe.NewFile(bytes.NewReader(original))
	if err != nil {
		return err
	}
	// EndUpdateResource can discard the COFF overlay while retaining its
	// header pointer. Go's long debug section names reference this string table.
	var symbols []byte
	if offset := uint64(coff.PointerToSymbolTable); offset != 0 {
		stringsAt := offset + uint64(coff.NumberOfSymbols)*18
		if stringsAt+4 > uint64(len(original)) {
			return fmt.Errorf("invalid COFF symbol table")
		}
		end := stringsAt + uint64(binary.LittleEndian.Uint32(original[stringsAt:]))
		if end > uint64(len(original)) || end < stringsAt+4 {
			return fmt.Errorf("invalid COFF string table")
		}
		symbols = original[offset:end]
	}
	data, err := os.ReadFile(icon)
	if err != nil {
		return err
	}
	if len(data) < 6 || binary.LittleEndian.Uint16(data[2:4]) != 1 {
		return fmt.Errorf("invalid ICO")
	}
	count := int(binary.LittleEndian.Uint16(data[4:6]))
	if count == 0 || len(data) < 6+16*count {
		return fmt.Errorf("invalid icon directory")
	}
	kernel := syscall.NewLazyDLL("kernel32.dll")
	begin := kernel.NewProc("BeginUpdateResourceW")
	update := kernel.NewProc("UpdateResourceW")
	end := kernel.NewProc("EndUpdateResourceW")
	path, err := syscall.UTF16PtrFromString(exe)
	if err != nil {
		return err
	}
	handle, _, err := begin.Call(uintptr(unsafe.Pointer(path)), 0)
	if handle == 0 {
		return err
	}
	committed := false
	defer func() {
		if !committed {
			end.Call(handle, 1)
		}
	}()
	write := func(kind, id uintptr, bytes []byte) error {
		ok, _, e := update.Call(handle, kind, id, 0x0804, uintptr(unsafe.Pointer(&bytes[0])), uintptr(len(bytes)))
		runtime.KeepAlive(bytes)
		if ok == 0 {
			return e
		}
		return nil
	}
	group := make([]byte, 6+14*count)
	copy(group, data[:6])
	for i := 0; i < count; i++ {
		entry := data[6+16*i : 6+16*(i+1)]
		length := int(binary.LittleEndian.Uint32(entry[8:12]))
		offset := int(binary.LittleEndian.Uint32(entry[12:16]))
		if offset < 0 || length <= 0 || offset > len(data)-length {
			return fmt.Errorf("invalid icon image")
		}
		copy(group[6+14*i:], entry[:12])
		binary.LittleEndian.PutUint16(group[6+14*i+12:], uint16(i+1))
		if err = write(3, uintptr(i+1), data[offset:offset+length]); err != nil {
			return err
		}
	}
	if err = write(14, 1, group); err != nil {
		return err
	}
	if err = write(24, 1, []byte(manifest)); err != nil {
		return err
	}
	ok, _, err := end.Call(handle, 0)
	if ok == 0 {
		return err
	}
	committed = true
	if len(symbols) != 0 {
		updated, err := os.ReadFile(exe)
		if err != nil {
			return err
		}
		peOffset := int(binary.LittleEndian.Uint32(updated[60:64]))
		binary.LittleEndian.PutUint32(updated[peOffset+12:], uint32(len(updated)))
		updated = append(updated, symbols...)
		if _, err = pe.NewFile(bytes.NewReader(updated)); err != nil {
			return fmt.Errorf("invalid PE after adding resources: %w", err)
		}
		if err = os.WriteFile(exe, updated, 0755); err != nil {
			return err
		}
	}
	return nil
}

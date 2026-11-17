// Package main builds the c-shared library used by Flutter via dart:ffi.
// It is not a standalone server; use cmd/engine for that.
package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"context"
	"encoding/json"
	"sync"
	"time"
	"unsafe"

	"strata/engine/internal/engine"
)

var (
	mu      sync.Mutex
	current *engine.Engine
)

type startResult struct {
	OK            bool   `json:"ok"`
	Addr          string `json:"addr,omitempty"`
	SeedVersion   string `json:"seed_version,omitempty"`
	BookCount     int    `json:"book_count,omitempty"`
	LicensedCount int    `json:"licensed_count,omitempty"`
	ContentEnd    string `json:"content_end,omitempty"`
	Error         string `json:"error,omitempty"`
}

func reply(v startResult) *C.char {
	data, err := json.Marshal(v)
	if err != nil {
		return C.CString(`{"ok":false,"error":"encode result"}`)
	}
	return C.CString(string(data))
}

//export strata_start
func strata_start(assetsDir, dataDir *C.char) *C.char {
	mu.Lock()
	defer mu.Unlock()

	// Idempotent: if the engine is already running in this process, report
	// its live state instead of failing (Flutter may recreate the activity
	// without killing the process).
	if current != nil {
		e := current
		m := e.Manifest()
		return reply(startResult{
			OK:            true,
			Addr:          e.Addr(),
			SeedVersion:   m.SeedVersion,
			BookCount:     m.BookCount,
			LicensedCount: m.LicensedCount,
			ContentEnd:    m.ContentEnd,
		})
	}
	e, err := engine.Start(C.GoString(assetsDir), C.GoString(dataDir))
	if err != nil {
		return reply(startResult{Error: err.Error()})
	}
	current = e
	m := e.Manifest()
	return reply(startResult{
		OK:            true,
		Addr:          e.Addr(),
		SeedVersion:   m.SeedVersion,
		BookCount:     m.BookCount,
		LicensedCount: m.LicensedCount,
		ContentEnd:    m.ContentEnd,
	})
}

//export strata_stop
func strata_stop() *C.char {
	mu.Lock()
	e := current
	current = nil
	mu.Unlock()

	if e == nil {
		return reply(startResult{OK: true})
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := e.Shutdown(ctx); err != nil {
		return reply(startResult{Error: err.Error()})
	}
	return reply(startResult{OK: true})
}

//export strata_free
func strata_free(p *C.char) {
	C.free(unsafe.Pointer(p))
}

func main() {}

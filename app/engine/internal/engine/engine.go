// Package engine wires the seed, user database, and HTTP API into one
// in-process service. It is shared by the CLI and the c-shared FFI entry.
package engine

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"sync"
	"time"

	"strata/engine/internal/api"
	"strata/engine/internal/appshell"
	"strata/engine/internal/store"
)

type Engine struct {
	manifest *appshell.Manifest
	store    *store.Store
	listener net.Listener
	server   *http.Server
	done     chan error

	closeOnce sync.Once
}

// Start resolves assets/data locations, installs the seed if needed, and
// begins serving on a dynamic loopback port.
func Start(assetsDir, dataDir string) (*Engine, error) {
	if assetsDir == "" {
		return nil, fmt.Errorf("assets directory is required")
	}
	if dataDir == "" {
		return nil, fmt.Errorf("data directory is required")
	}
	return StartPaths(appshell.Paths{AssetsDir: assetsDir, DataDir: dataDir})
}

// StartWithFlags resolves paths using the same rules as the CLI.
func StartWithFlags(assetsFlag, dataFlag string) (*Engine, error) {
	paths, err := appshell.ResolvePaths(assetsFlag, dataFlag)
	if err != nil {
		return nil, err
	}
	return StartPaths(paths)
}

func StartPaths(paths appshell.Paths) (*Engine, error) {
	manifest, err := appshell.LoadManifest(paths.AssetsDir)
	if err != nil {
		return nil, err
	}
	seedPath, err := appshell.InstallSeed(paths.AssetsDir, paths.DataDir, manifest)
	if err != nil {
		return nil, err
	}
	userPath := appshell.UserDBPath(paths.DataDir)
	if err := appshell.EnsureUserDB(userPath); err != nil {
		return nil, fmt.Errorf("user.db: %w", err)
	}

	st, err := store.Open(userPath, seedPath, manifest)
	if err != nil {
		return nil, err
	}
	// Retention (docs 02 §3.1): drop observations older than 180 days at
	// startup; user.db only.
	if n, err := st.PruneObservations(context.Background(), time.Now()); err != nil {
		st.Close()
		return nil, fmt.Errorf("prune observations: %w", err)
	} else if n > 0 {
		fmt.Printf("STRATA_PRUNED=%d\n", n)
	}

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		st.Close()
		return nil, err
	}

	e := &Engine{
		manifest: manifest,
		store:    st,
		listener: listener,
		server: &http.Server{
			Handler:           api.New(st),
			ReadHeaderTimeout: 5 * time.Second,
		},
		done: make(chan error, 1),
	}
	go e.serve()
	return e, nil
}

func (e *Engine) serve() {
	err := e.server.Serve(e.listener)
	if errors.Is(err, http.ErrServerClosed) {
		err = nil
	}
	e.closeStore()
	e.done <- err
}

func (e *Engine) closeStore() {
	e.closeOnce.Do(func() {
		_ = e.store.Close()
	})
}

func (e *Engine) Addr() string {
	return "http://" + e.listener.Addr().String()
}

func (e *Engine) Manifest() *appshell.Manifest {
	return e.manifest
}

// Done receives the final serve result. It yields once.
func (e *Engine) Done() <-chan error {
	return e.done
}

func (e *Engine) Shutdown(ctx context.Context) error {
	err := e.server.Shutdown(ctx)
	e.closeStore()
	return err
}

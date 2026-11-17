package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"strata/engine/internal/api"
	"strata/engine/internal/appshell"
	"strata/engine/internal/store"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "engine:", err)
		os.Exit(1)
	}
}

func run() error {
	assetsFlag := flag.String("assets", "", "directory containing manifest.json + seed.db.gz")
	dataFlag := flag.String("data-dir", "", "writable app data directory")
	flag.Parse()

	paths, err := appshell.ResolvePaths(*assetsFlag, *dataFlag)
	if err != nil {
		return err
	}
	manifest, err := appshell.LoadManifest(paths.AssetsDir)
	if err != nil {
		return err
	}
	seedPath, err := appshell.InstallSeed(paths.AssetsDir, paths.DataDir, manifest)
	if err != nil {
		return err
	}
	userPath := appshell.UserDBPath(paths.DataDir)
	if err := appshell.EnsureUserDB(userPath); err != nil {
		return fmt.Errorf("user.db: %w", err)
	}

	st, err := store.Open(userPath, seedPath, manifest)
	if err != nil {
		return err
	}
	defer st.Close()

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return err
	}
	server := &http.Server{
		Handler:           api.New(st),
		ReadHeaderTimeout: 5 * time.Second,
	}

	fmt.Printf("STRATA_ADDR=http://%s\n", listener.Addr().String())
	fmt.Printf("STRATA_SEED=%s\n", manifest.SeedVersion)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	serveErr := make(chan error, 1)
	go func() { serveErr <- server.Serve(listener) }()

	select {
	case err := <-serveErr:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return server.Shutdown(shutdownCtx)
	}
}

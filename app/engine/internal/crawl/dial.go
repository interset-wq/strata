package crawl

import (
	"context"
	"net"
	"sync"
	"time"
)

// HostsDialer dials candidate IPs for well-known hosts, preferring a static
// override table (device-side DNS can be poisoned: the wrong IP answers TLS
// with a certificate that does not match the requested host). TLS ServerName
// stays the hostname, so certificate verification is unaffected.
type HostsDialer struct {
	// Hosts maps hostname → candidate IP overrides, tried before any
	// resolved address.
	Hosts map[string][]string

	// Timeout bounds each TCP connect.
	Timeout time.Duration

	mu sync.RWMutex
}

// NewHostsDialer builds a dialer with the given static overrides.
func NewHostsDialer(hosts map[string][]string, timeout time.Duration) *HostsDialer {
	return &HostsDialer{Hosts: hosts, Timeout: timeout}
}

// DialContext implements http.Transport's dialer.
func (d *HostsDialer) DialContext(ctx context.Context, network, address string) (net.Conn, error) {
	host, port, err := net.SplitHostPort(address)
	if err != nil {
		return nil, err
	}
	if ip := net.ParseIP(host); ip != nil {
		nd := net.Dialer{Timeout: d.Timeout}
		return nd.DialContext(ctx, network, address)
	}

	var candidates []string
	d.mu.RLock()
	for _, ip := range d.Hosts[host] {
		candidates = append(candidates, net.JoinHostPort(ip, port))
	}
	d.mu.RUnlock()

	if ips, err := net.DefaultResolver.LookupHost(ctx, host); err == nil {
		for _, ip := range ips {
			candidates = append(candidates, net.JoinHostPort(ip, port))
		}
	}
	if len(candidates) == 0 {
		return nil, &net.DNSError{Err: "no address", Name: host}
	}

	nd := net.Dialer{Timeout: d.Timeout}
	var lastErr error
	for _, cand := range candidates {
		conn, derr := nd.DialContext(ctx, network, cand)
		if derr == nil {
			return conn, nil
		}
		lastErr = derr
	}
	return nil, lastErr
}

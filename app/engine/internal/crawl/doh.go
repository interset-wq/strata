package crawl

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"sync"
	"time"
)

// dohDialer resolves hostnames through a DNS-over-HTTPS JSON API
// (AliDNS 223.5.5.5) and dials the returned IPs. Bootstrap needs no DNS:
// 223.5.5.5 is an IP whose TLS cert carries an IP SAN.
type dohDialer struct {
	// Endpoint is the DoH JSON URL, e.g. https://223.5.5.5/resolve.
	Endpoint string

	// DialTimeout bounds the TCP connect to the target host.
	DialTimeout time.Duration

	mu    sync.Mutex
	cache map[string][]net.IP
	ttl   map[string]time.Time
}

// NewDohDialer returns a dialer that resolves hostnames through the DoH
// endpoint and dials the returned IPs.
func NewDohDialer() *dohDialer {
	return &dohDialer{
		Endpoint:    "https://223.5.5.5/resolve",
		DialTimeout: 10 * time.Second,
		cache:       map[string][]net.IP{},
		ttl:         map[string]time.Time{},
	}
}

var dohClient = &http.Client{Timeout: 10 * time.Second}

func (d *dohDialer) lookup(ctx context.Context, host string) ([]net.IP, error) {
	d.mu.Lock()
	if ips, ok := d.cache[host]; ok && time.Now().Before(d.ttl[host]) {
		d.mu.Unlock()
		return ips, nil
	}
	d.mu.Unlock()

	url := fmt.Sprintf("%s?name=%s&type=A", d.Endpoint, host)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := dohClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("doh lookup %s: %w", host, err)
	}
	defer resp.Body.Close()
	var body struct {
		Answer []struct {
			Data string `json:"data"`
		} `json:"Answer"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, fmt.Errorf("doh decode %s: %w", host, err)
	}
	var ips []net.IP
	for _, a := range body.Answer {
		if ip := net.ParseIP(a.Data); ip != nil && ip.To4() != nil {
			ips = append(ips, ip)
		}
	}
	if len(ips) == 0 {
		return nil, fmt.Errorf("doh: no A record for %s", host)
	}
	d.mu.Lock()
	d.cache[host] = ips
	d.ttl[host] = time.Now().Add(5 * time.Minute)
	d.mu.Unlock()
	return ips, nil
}

// DialContext implements the http.Transport dialer signature. TLS ServerName
// stays the original hostname, so certificate validation is unaffected.
func (d *dohDialer) DialContext(ctx context.Context, network, address string) (net.Conn, error) {
	host, port, err := net.SplitHostPort(address)
	if err != nil {
		return nil, err
	}
	if ip := net.ParseIP(host); ip != nil {
		nd := net.Dialer{Timeout: d.DialTimeout}
		return nd.DialContext(ctx, network, address)
	}
	ips, err := d.lookup(ctx, host)
	if err != nil {
		return nil, err
	}
	nd := net.Dialer{Timeout: d.DialTimeout}
	var lastErr error
	for _, ip := range ips {
		conn, derr := nd.DialContext(ctx, network, net.JoinHostPort(ip.String(), port))
		if derr == nil {
			return conn, nil
		}
		lastErr = derr
	}
	return nil, lastErr
}

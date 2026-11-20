package crawl

import (
	"os"
	"strings"
	"testing"
)

// Golden test: the fixture is a real archived search page (2026-11-20,
// keyword 英雄, 29/29 rows — the page drifts slightly over time, so
// assert structure and the head row, not exact strings everywhere).
func TestParseSearchFixture(t *testing.T) {
	raw, err := os.ReadFile("testdata/search_hero.html")
	if err != nil {
		t.Fatalf("fixture: %v", err)
	}
	res := ParseSearch(string(raw))
	if res.Throttled {
		t.Fatal("fixture must not be throttled")
	}
	if res.Declared != 29 {
		t.Fatalf("declared = %d", res.Declared)
	}
	if len(res.Items) != 29 {
		t.Fatalf("items = %d, want 29", len(res.Items))
	}
	first := res.Items[0]
	if first.NID != 48704 || first.Title == "" || first.Author == "" {
		t.Fatalf("first = %+v", first)
	}
	if first.CoverURL == "" || !strings.HasPrefix(first.CoverURL, "https://") {
		t.Fatalf("cover = %q", first.CoverURL)
	}
	if first.UpdatedAt == "" {
		t.Fatal("empty updated_at")
	}
}

func TestParseSearchThrottled(t *testing.T) {
	// Synthetic: the throttle fingerprint is the probe-verified verdict
	// (docs/sfacg-endpoints.md §2.1) — HTTP 200, structurally normal
	// page, search box label flipped. Only this string distinguishes it.
	html := `<html><head><title>请输入关键字</title></head><body>
		<div>共搜索到 0 个结果</div></body></html>`
	res := ParseSearch(html)
	if res == nil {
		t.Fatal("nil result")
	}
	if !res.Throttled || len(res.Items) != 0 {
		t.Fatalf("throttled = %v, items = %d", res.Throttled, len(res.Items))
	}
}

func TestParseSearchEmpty(t *testing.T) {
	// A legit zero-hit page: same structure, no throttle fingerprint.
	html := `<html><body><div>共搜索到 0 个结果</div></body></html>`
	res := ParseSearch(html)
	if res == nil || res.Throttled {
		t.Fatalf("throttled = %v", res)
	}
	if len(res.Items) != 0 || res.Declared != 0 {
		t.Fatalf("declared = %d, items = %d", res.Declared, len(res.Items))
	}
}

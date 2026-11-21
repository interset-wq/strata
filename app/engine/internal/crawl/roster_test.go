package crawl

import (
	"os"
	"testing"
)

func readRosterFixture(t *testing.T, name string) string {
	t.Helper()
	b, err := os.ReadFile("testdata/" + name)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func TestParseRosterNew(t *testing.T) {
	p := ParseRosterNew(readRosterFixture(t, "roster_new.json"))
	if p == nil {
		t.Fatal("nil page for valid body")
	}
	if p.TotalPage != 2 {
		t.Fatalf("totalPage = %d, want 2", p.TotalPage)
	}
	if len(p.Entries) != 2 {
		t.Fatalf("entries = %d, want 2 (placeholder nid=0 dropped)", len(p.Entries))
	}
	e0 := p.Entries[0]
	if e0.NID != 713638 || e0.Title != "Re：如果成为神明" || e0.Author != "某NoName" {
		t.Fatalf("entry0 = %+v", e0)
	}
	if e0.CategoryID != 3 {
		t.Fatalf("categoryID = %d, want 3", e0.CategoryID)
	}
	wantCover := "https://rs.sfacg.com/web/novel/images/NovelCover/Big/2024/08/daea837b-bce6-4ca1-98c0-9a945c730a9f.jpg"
	if e0.Cover != wantCover {
		t.Fatalf("cover = %q, want %q", e0.Cover, wantCover)
	}
	if e0.Intro == "" {
		t.Fatal("intro lost")
	}
	e1 := p.Entries[1]
	// cleanText trims the padded title; null author/intro stay empty.
	if e1.Title != "测试长篇作品" || e1.Author != "" || e1.Intro != "" {
		t.Fatalf("entry1 = %+v", e1)
	}
}

func TestParseRosterNewDead(t *testing.T) {
	if p := ParseRosterNew(readRosterFixture(t, "roster_new_dead.json")); p != nil {
		t.Fatalf("dead body parsed: %+v", p)
	}
	if p := ParseRosterNew(readRosterFixture(t, "roster_new_empty.json")); p == nil {
		t.Fatal("empty-but-alive body should parse to an empty page")
	} else if len(p.Entries) != 0 || p.TotalPage != 1 {
		t.Fatalf("empty page = %+v", p)
	}
	if p := ParseRosterNew("not json"); p != nil {
		t.Fatal("malformed body parsed")
	}
}

func TestParseRosterOld(t *testing.T) {
	p := ParseRosterOld(readRosterFixture(t, "roster_old.json"))
	if p == nil {
		t.Fatal("nil page for valid body")
	}
	if p.TotalPage != 3 {
		t.Fatalf("totalPage = %d, want 3", p.TotalPage)
	}
	if len(p.Entries) != 2 {
		t.Fatalf("entries = %d, want 2", len(p.Entries))
	}
	e0 := p.Entries[0]
	if e0.NID != 277050 || e0.Author != "鱼鱼鱼干" {
		t.Fatalf("entry0 = %+v", e0)
	}
	// cover fragment gets the CDN prefix.
	wantCover := "https://rs.sfacg.com/web/novel/images/NovelCover/Big/2020-09-09/df267749-ceed-42f9-8fd3-964cc62c149e.jpg"
	if e0.Cover != wantCover {
		t.Fatalf("cover = %q, want %q", e0.Cover, wantCover)
	}
	e1 := p.Entries[1]
	if e1.NID != 990002 || e1.CategoryID != 3 || e1.Author != "" {
		t.Fatalf("entry1 = %+v", e1)
	}
}

func TestParseRosterOldDead(t *testing.T) {
	if p := ParseRosterOld(readRosterFixture(t, "roster_old_dead.json")); p != nil {
		t.Fatalf("dead body parsed: %+v", p)
	}
	if p := ParseRosterOld("not json"); p != nil {
		t.Fatal("malformed body parsed")
	}
}

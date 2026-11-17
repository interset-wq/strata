package store

import (
	"context"
	"errors"
	"testing"

	"strata/engine/internal/appshell"
	"strata/engine/internal/testseed"
)

func openTestStore(t *testing.T) *Store {
	t.Helper()
	assets, data := t.TempDir(), t.TempDir()
	m, err := testseed.Build(assets, data)
	if err != nil {
		t.Fatal(err)
	}
	seedPath, err := appshell.InstallSeed(assets, data, m)
	if err != nil {
		t.Fatal(err)
	}
	st, err := Open(appshell.UserDBPath(data), seedPath, m)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { st.Close() })
	return st
}

func TestBookMergesLatestObservation(t *testing.T) {
	st := openTestStore(t)
	detail, err := st.Book(context.Background(), 1001)
	if err != nil {
		t.Fatal(err)
	}
	if detail.Book.Favs == nil || *detail.Book.Favs != 500 {
		t.Fatalf("seed favs = %v", detail.Book.Favs)
	}
	if detail.Local == nil || detail.Local.Favs == nil || *detail.Local.Favs != 777 {
		t.Fatalf("local favs = %+v", detail.Local)
	}
	if len(detail.Tags) != 2 || detail.Tags[0] != "战斗" && detail.Tags[0] != "热血" {
		t.Fatalf("tags = %v", detail.Tags)
	}
}

func TestLicensedBookHasNoPercentiles(t *testing.T) {
	st := openTestStore(t)
	detail, err := st.Book(context.Background(), 2001)
	if err != nil {
		t.Fatal(err)
	}
	if !detail.Book.IsLicensed {
		t.Fatal("nid 2001 should be licensed")
	}
	if detail.Book.FavPctl != nil || detail.Book.PctlPR != nil {
		t.Fatalf("licensed percentiles = %v / %v", detail.Book.FavPctl, detail.Book.PctlPR)
	}
	if detail.Local != nil {
		t.Fatal("unexpected local observation")
	}
}

func TestBookNotFound(t *testing.T) {
	st := openTestStore(t)
	_, err := st.Book(context.Background(), 999999)
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("err = %v", err)
	}
}

func TestRankingFavsExcludesLicensedAndOtherYears(t *testing.T) {
	st := openTestStore(t)
	items, err := st.RankingFavs(context.Background(), 2010, "", "", "", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 3 {
		t.Fatalf("items = %d, want 3", len(items))
	}
	if items[0].NID != 1001 || items[0].FavPctl != 0.9 || items[0].Rank != 1 {
		t.Fatalf("first = %+v", items[0])
	}
	for _, item := range items {
		if item.NID == 2001 {
			t.Fatal("licensed book leaked into A-class ranking")
		}
	}
}

func TestRankingFavsGenreFilter(t *testing.T) {
	st := openTestStore(t)
	items, err := st.RankingFavs(context.Background(), 2010, "魔幻", "", "", 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].NID != 1001 || items[1].NID != 1004 {
		t.Fatalf("items = %+v", items)
	}
}

func TestRankingShort(t *testing.T) {
	st := openTestStore(t)
	items, err := st.RankingShort(context.Background(), 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].NID != 1002 || items[1].NID != 1004 {
		t.Fatalf("items = %+v", items)
	}
	if items[0].Words == nil || *items[0].Words != 30000 {
		t.Fatalf("words = %v", items[0].Words)
	}
}

func TestSeedMeta(t *testing.T) {
	st := openTestStore(t)
	meta, err := st.SeedMeta(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if meta["book_count"] != "6" || meta["licensed_count"] != "1" {
		t.Fatalf("meta = %v", meta)
	}
}

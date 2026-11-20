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

// TestBannerPickDailySeedChangesOrder pins the 2026-11-20 fix: with the
// old additive hash (nid*a + day) the day advanced the cut point by one
// bucket in the 1,000,003-bucket space, so consecutive days returned the
// identical top-k (user reported today == yesterday). The XOR hash must
// reorder the pool on consecutive days and stay deterministic per seed.
func TestBannerPickDailySeedChangesOrder(t *testing.T) {
	st := openTestStore(t)
	ctx := context.Background()

	a, err := st.BannerPick(ctx, 20261119, 0, 100, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(a) < 2 {
		t.Fatalf("featured pool too small: %d", len(a))
	}
	b, err := st.BannerPick(ctx, 20261120, 0, 100, "")
	if err != nil {
		t.Fatal(err)
	}
	if sameNidOrder(a, b) {
		t.Fatalf("consecutive-day orders identical: %+v", a)
	}
	// Determinism: the same seed returns the same order.
	c, err := st.BannerPick(ctx, 20261119, 0, 100, "")
	if err != nil {
		t.Fatal(err)
	}
	if !sameNidOrder(a, c) {
		t.Fatalf("same seed, different order: %+v vs %+v", a, c)
	}
}

func sameNidOrder(a, b []FeaturedBook) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i].NID != b[i].NID {
			return false
		}
	}
	return true
}

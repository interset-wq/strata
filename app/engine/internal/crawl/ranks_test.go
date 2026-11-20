package crawl

import (
	"os"
	"path/filepath"
	"testing"
)

func readTestdata(t *testing.T, name string) string {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("testdata", name))
	if err != nil {
		t.Fatalf("read testdata %s: %v", name, err)
	}
	return string(b)
}

// Golden: the PC Rank page (2026-11-20 capture) — four boards, 月票 with
// 票数, 打赏/热销 without, 粉丝 reader-side (no nid) 月 tab only.
func TestParsePcRanks(t *testing.T) {
	boards := ParsePcRanks(readTestdata(t, "pc_rank.html"))
	if len(boards) != 4 {
		t.Fatalf("boards = %d, want 4 (names: %v)", len(boards), boardNames(boards))
	}
	wantNames := []string{"月度月票榜", "月度打赏榜", "月度热销榜", "粉丝榜"}
	for i, b := range boards {
		if b.Name != wantNames[i] {
			t.Errorf("board %d name = %q, want %q", i, b.Name, wantNames[i])
		}
	}
	// 月票榜 top row: nid + 票数.
	top := boards[0].Entries[0]
	if top.NID != 750700 || top.Title != "黑道公主的我还能怎么堕落？" || top.Value != 3228 {
		t.Errorf("月票 top = %+v, want nid 750700 票数 3228", top)
	}
	// 打赏榜 rows have no 票数.
	if boards[1].Entries[0].Value != 0 || boards[1].Entries[0].NID != 750700 {
		t.Errorf("打赏 top = %+v, want nid 750700 value 0", boards[1].Entries[0])
	}
	// 粉丝榜 rows are reader-side: no nid, 火券 value present.
	if boards[3].Entries[0].NID != 0 || boards[3].Entries[0].Title != "椿秋分" ||
		boards[3].Entries[0].Value != 214389 {
		t.Errorf("粉丝 top = %+v, want user 椿秋分 火券 214389", boards[3].Entries[0])
	}
	// All four boards must be non-empty.
	for i, b := range boards {
		if len(b.Entries) == 0 {
			t.Errorf("board %d (%s) is empty", i, b.Name)
		}
	}
}

func boardNames(boards []PcBoard) []string {
	out := make([]string, len(boards))
	for i, b := range boards {
		out[i] = b.Name
	}
	return out
}

// Golden: the mobile 人气榜 (2026-11-20 capture) — 20 rows, nid + title +
// 作者/题材, no values.
func TestParseMobileRank(t *testing.T) {
	items := ParseMobileRank(readTestdata(t, "mrank_original.html"))
	if len(items) != 20 {
		t.Fatalf("items = %d, want 20", len(items))
	}
	top := items[0]
	if top.NID != 400179 || top.Title != "反派再生后不想跟美少女纠缠" ||
		top.Author != "滑稽罐头" || top.Genre != "玄幻" {
		t.Errorf("top = %+v, want 400179 反派再生后不想跟美少女纠缠 滑稽罐头/玄幻", top)
	}
	last := items[19]
	if last.NID != 400412 || last.Title != "今天的魔女小姐也在努力活着" {
		t.Errorf("last = %+v, want 400412 今天的魔女小姐也在努力活着", last)
	}
	for i, it := range items {
		if it.Value != 0 {
			t.Errorf("item %d carries value %d, mobile boards have none", i, it.Value)
		}
	}
}

// Golden: the MonthlyBoy.ashx JSON (2013-03 sample) — placeholder rows with
// nid 0 are dropped, 票数 preserved.
func TestParseMonthlyRanks(t *testing.T) {
	items := ParseMonthlyRanks(readTestdata(t, "monthly_ranks_sample.json"))
	if len(items) != 2 {
		t.Fatalf("items = %d, want 2 (placeholder dropped)", len(items))
	}
	top := items[0]
	if top.NID != 7661 || top.Title != "魂武纪" || top.Value != 53 ||
		top.Author != "loydysky" || top.Rank != 1 {
		t.Errorf("top = %+v, want 7661 魂武纪 53 loydsyky rank 1", top)
	}
	if items[1].Rank != 2 || items[1].NID != 7845 {
		t.Errorf("second = %+v, want rank 2 nid 7845", items[1])
	}
	if items[0].CoverURL == "" {
		t.Error("top cover url missing")
	}
}

package store

// 相关推荐（docs/related-books.md v5）：以当前书为锚点的强标签分级召回 +
// 档内分层/轮流/打散。纯 seed 本地查询、无网络。
//
// 用户裁定（2026-11-26）：所有自定义指标（cqs/cps/pr）只能决定「已选中书籍
// 的展示顺序」，绝不能影响「哪些书进入候选/被选中」。v4.1 把 cqs/pr 同时用作
// 候选门槛与选书排序，导致高指标书在每个组里都胜出、跨锚点被高频推荐
// （随机 300 锚点重复率 66.4%、单本最高 19 次）。v5 把指标从 WHERE/选书 ORDER BY
// 全部移除，只在选满 limit 后按指标排展示顺序：重复率降到 21.3%、命中率反升。
//
// 封面同样不是判断依据（用户 2026-11-26 裁定）：sfacg 曾弄丢大量优质书的
// cover，cover 为空是源站数据事故、不是作品质量信号。cover 只 SELECT 出来
// 供展示，空值由 UI 的 coverImage 本地占位兜底，绝不进候选 WHERE / 选书 / 排序。
//
// 累计值 clicks/favs/praises 只 SELECT 不参与任何排序（docs/12 §3.2 红线）；
// favs 仅作平滑 pr 的分母（与 cqs 同公式）。

import (
	"context"
	"database/sql"
	"fmt"
	"sort"
	"strings"
)

// RelatedResult 是一次相关推荐的结果：rail 条目 + 锚点 form/genre + 召回档 +
// 排序键（docs §4：tier/ordering 只供诊断，不向用户展示指标名）。
type RelatedResult struct {
	Items    []RankItem
	Form     string
	Genre    string
	Tier     string // a | b | c | fallback | none
	Ordering string // cqs | pr
}

// 强标签：全库 df ≤ 1000（约 6%）才算核心卖点；更泛的是分类噪音，
// 只用于 B 档打散、不进排序分（docs §3.3）。
const strongTagMaxDF = 1000

// 极稀疏标签：df ≤ 100 的标签同类极少且常跨代（师尊 28 / 超级英雄 64），
// 世代窗口从 ±3 放宽到 ±8（docs §3.4）。
const sparseTagMaxDF = 100

const (
	relatedWindowYear   = 3
	relatedWindowSparse = 8
	relatedWindowB      = 5
	relatedPoolFactor   = 12
	relatedPoolMax      = 150
)

type relatedAnchor struct {
	nid    int64
	form   string
	genre  string
	year   int
	author string
}

type relatedCand struct {
	item  RankItem
	score float64 // 自定义指标（cqs / 平滑 pr）：只用于选中后的展示排序，不进候选/选书
	ovl   int      // 与锚点的全标签重叠数（B 档打散键，内容信号）
	hits  []string // 命中的锚点强标签（A′/C′ 分层键，内容信号）
}

// relatedGate 只提供展示排序用的平滑 pr 参数（mu0）。
// v5 起指标不再进候选 WHERE、不进选书 ORDER BY（用户 2026-11-26 裁定）：
// 候选/选书全用内容信号（题材/标签/世代/重叠数），指标只决定已选中书的展示顺序。
type relatedGate struct {
	mu float64
}

// RelatedBooks 按 docs/related-books.md §3 出相关推荐：先排除（授权 47 本、
// 跨 form、同作者、当前书），不因缺封面排除（源站丢图是数据事故，非质量信号），
// 再 A′ → B → C′ → 同 form 口碑末档逐级降档凑满 limit。锚点无 form 时不推
// （tier=none，UI 整行隐藏）。
func (s *Store) RelatedBooks(ctx context.Context, anchorNID int64, limit int) (RelatedResult, error) {
	res := RelatedResult{Items: []RankItem{}, Tier: "none", Ordering: "cqs"}
	if limit <= 0 {
		limit = 8
	}
	a, err := s.relatedAnchor(ctx, anchorNID)
	if err != nil {
		return res, err
	}
	if a.form == "" {
		return res, nil
	}
	res.Form, res.Genre = a.form, a.genre

	// long/dialogue 用 cqs（18 §2 唯一可信处）；其余 form 无 cqs，用平滑 pr。
	res.Ordering = "pr"
	if a.form == "long" || a.form == "dialogue" {
		res.Ordering = "cqs"
	}
	gate, err := s.relatedGate(ctx)
	if err != nil {
		return res, err
	}

	anchorTags, err := s.bookTags(ctx, anchorNID)
	if err != nil {
		return res, err
	}
	df, err := s.tagDF(ctx, anchorTags)
	if err != nil {
		return res, err
	}
	strong := make([]string, 0, len(anchorTags))
	sparse := false
	for _, t := range anchorTags {
		if isOperationalTag(t) || df[t] == 0 || df[t] > strongTagMaxDF {
			continue
		}
		strong = append(strong, t)
		if df[t] <= sparseTagMaxDF {
			sparse = true
		}
	}
	window := relatedWindowYear
	if sparse {
		window = relatedWindowSparse
	}
	// 回填书 est_year=0001/0：|Δyear| 失效，年代档全部让位（docs §9）。
	yearKnown := a.year >= 2000

	seen := map[int64]bool{a.nid: true}
	// scores 记录每本被选中书的展示排序键（cqs / 平滑 pr）。
	// 注意：score 只在这里（选满之后）用，绝不参与候选准入或选书顺序。
	scores := make(map[int64]float64, limit)
	for _, tier := range []struct {
		name   string
		enable bool
		strong bool // 需要强标签条件
	}{
		{"a", len(strong) > 0 && yearKnown && a.genre != "", true},
		{"b", a.genre != "", false},
		{"c", len(strong) > 0 && yearKnown, true},
		{"fallback", true, false},
	} {
		if !tier.enable || len(res.Items) >= limit {
			continue
		}
		cands, err := s.relatedPool(ctx, a, tier.name, strong, anchorTags, gate, window, limit)
		if err != nil {
			return res, err
		}
		if len(cands) == 0 {
			continue
		}
		if tier.strong {
			if err := s.relatedHits(ctx, strong, cands); err != nil {
				return res, err
			}
			sortRelatedStrata(df, cands)
		}
		for _, c := range cands {
			if len(res.Items) >= limit {
				break
			}
			if seen[c.item.NID] {
				continue
			}
			seen[c.item.NID] = true
			res.Items = append(res.Items, c.item)
			scores[c.item.NID] = c.score
			// tier 回显"最浅到哪一档"，即贡献了条目的最后一档：rail 尾部来自
			// 哪一档决定用户看到的相关性，只有重复候选被去重的档不算。
			res.Tier = tier.name
		}
	}
	// v5 唯一用指标的地方：对已选中的 limit 本按 cqs / 平滑 pr 排展示顺序。
	// 无指标值（cqs=NULL）的垫底、nid 升序打破平手，保证顺序确定可复现。
	sort.SliceStable(res.Items, func(i, j int) bool {
		si, sji := scores[res.Items[i].NID], scores[res.Items[j].NID]
		if si != sji {
			return si > sji
		}
		return res.Items[i].NID < res.Items[j].NID
	})
	s.attachTags(ctx, res.Items)
	return res, nil
}

// relatedAnchor 按收录均等原则取锚点字段：seed.books → 已评分 discovered →
// book_meta（docs/08 §recommend 同源）。库外书没有标签表可查，只能走 B 档。
func (s *Store) relatedAnchor(ctx context.Context, nid int64) (relatedAnchor, error) {
	a := relatedAnchor{nid: nid}
	var genre sql.NullString
	err := s.DB.QueryRowContext(ctx, `
SELECT form, genre, est_year, author FROM seed.books WHERE nid = ?`,
		nid).Scan(&a.form, &genre, &a.year, &a.author)
	if err == nil {
		a.genre = genre.String
		return a, nil
	}
	if err != sql.ErrNoRows {
		return a, err
	}
	// 库外书：只有刷出过详情（cqs 非空）的 discovered 才带 form/genre。
	err = s.DB.QueryRowContext(ctx, `
SELECT form, genre, est_year, author FROM discovered
WHERE nid = ? AND cqs IS NOT NULL`, nid).Scan(&a.form, &genre, &a.year, &a.author)
	if err == nil {
		a.genre = genre.String
		return a, nil
	}
	if err != sql.ErrNoRows {
		return a, err
	}
	err = s.DB.QueryRowContext(ctx, `
SELECT form, genre, est_year, author FROM book_meta WHERE nid = ?`,
		nid).Scan(&a.form, &genre, &a.year, &a.author)
	if err == sql.ErrNoRows {
		return a, nil
	}
	if err == nil {
		a.genre = genre.String
	}
	return a, err
}

// relatedGate 只取展示排序用的平滑 pr 参数（κ=500、μ0 取 seed_meta，18 §1）。
// v5 起不再产出候选 WHERE / 选书 ORDER BY：自定义指标不得决定哪些书被推荐
// （用户 2026-11-26 裁定），cqs/cps/pr 的门槛与中层带全部移除。
func (s *Store) relatedGate(ctx context.Context) (relatedGate, error) {
	var mu0 sql.NullString
	if err := s.DB.QueryRowContext(ctx,
		"SELECT value FROM seed.seed_meta WHERE key = 'cqs_mu0'").Scan(&mu0); err != nil && err != sql.ErrNoRows {
		return relatedGate{}, err
	}
	mu := 0.232
	if mu0.Valid {
		var v float64
		if _, err := fmt.Sscanf(mu0.String, "%g", &v); err == nil && v > 0 {
			mu = v
		}
	}
	return relatedGate{mu: mu}, nil
}

// relatedPool 查一档候选：SQL 只负责硬门槛 + 档条件 + 内容信号粗排，多取若干条
// 交给 Go 侧分层/轮流重排（A′/C′）。自定义指标（score 列）与封面（cover_url）
// 都只 SELECT 出来：前者供 RelatedBooks 选满后排展示顺序，后者供 UI 展示，
// 两者绝不进 WHERE / ORDER BY（用户 2026-11-26 裁定：指标与 cover 均不作判断依据）。
func (s *Store) relatedPool(ctx context.Context, a relatedAnchor, tier string,
	strong, anchorTags []string, gate relatedGate, window, limit int) ([]relatedCand, error) {

	// 参数必须按 SQL 文本里 ? 的出现顺序入列：SELECT 的 ovl 子查询最靠前，
	// 其次 WHERE 的 form/nid/author，再是各档条件，最后 ORDER BY / LIMIT。
	args := []any{}

	// 全标签重叠数子查询（内容信号）：所有档都算，B/fallback 用它粗排打散。
	// 它的占位符在 SELECT 列，必须先于 WHERE 参数入列。
	ovlTags := len(anchorTags) > 0
	var head []string
	if ovlTags {
		head = make([]string, len(anchorTags))
		for i, t := range anchorTags {
			head[i] = "?"
			args = append(args, t)
		}
	}
	args = append(args, a.form, a.nid, a.author)
	// A′/C′ 的强标签 EXISTS 占位在 WHERE 尾部，最后入列。
	strongPh := strings.TrimSuffix(strings.Repeat("?,", len(strong)), ",")

	// 展示排序键：long/dialogue 用 cqs（可能为 NULL），其余用贝叶斯平滑 pr。
	// 仅 SELECT 出来带入 cand.score，不参与本函数的任何 WHERE / ORDER BY。
	var scoreCol string
	if a.form == "long" || a.form == "dialogue" {
		scoreCol = "seed.books.cqs AS score"
	} else {
		scoreCol = fmt.Sprintf("(COALESCE(seed.books.praises, 0) + %.17g) / (seed.books.favs + 500.0) AS score",
			500*gate.mu)
	}
	ovlCol := "0 AS ovl"
	if ovlTags {
		ovlCol = fmt.Sprintf(`(SELECT COUNT(*) FROM seed.book_tags bt
         WHERE bt.nid = seed.books.nid AND bt.tag IN (%s)) AS ovl`,
			strings.Join(head, ","))
	}

	q := fmt.Sprintf(`
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.price_type,
       seed.books.words, seed.books.clicks, seed.books.favs, seed.books.praises,
       seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url,
       %s,
       %s
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE seed.books.is_licensed = 0
  -- cover 只取展示值，不做非空门槛：sfacg 丢过大量优质书封面，空值不是质量信号。
  AND seed.books.form = ?
  AND seed.books.nid <> ?
  AND seed.books.author <> ?`, scoreCol, ovlCol)

	switch tier {
	case "a":
		q += " AND seed.books.genre = ? AND ABS(seed.books.est_year - ?) <= ?"
		args = append(args, a.genre, a.year, window)
		q += fmt.Sprintf(` AND EXISTS (SELECT 1 FROM seed.book_tags bt
        WHERE bt.nid = seed.books.nid AND bt.tag IN (%s))`, strongPh)
		for _, t := range strong {
			args = append(args, t)
		}
	case "b":
		q += " AND seed.books.genre = ?"
		args = append(args, a.genre)
		if a.year >= 2000 {
			q += " AND ABS(seed.books.est_year - ?) <= ?"
			args = append(args, a.year, relatedWindowB)
		}
	case "c":
		q += " AND ABS(seed.books.est_year - ?) <= ?"
		args = append(args, a.year, window)
		q += fmt.Sprintf(` AND EXISTS (SELECT 1 FROM seed.book_tags bt
        WHERE bt.nid = seed.books.nid AND bt.tag IN (%s))`, strongPh)
		for _, t := range strong {
			args = append(args, t)
		}
	}
	// 粗排只用内容信号：全标签重叠数 DESC、年代接近、nid 升序。
	// 指标（score）绝不进 ORDER BY，否则高指标书在每档都排前、跨锚点高频重复。
	q += " ORDER BY ovl DESC, ABS(seed.books.est_year - ?) ASC, seed.books.nid ASC"
	args = append(args, a.year)
	q += " LIMIT ?"
	pool := limit * relatedPoolFactor
	if pool > relatedPoolMax {
		pool = relatedPoolMax
	}
	args = append(args, pool)

	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []relatedCand{}
	for rows.Next() {
		var (
			c                                relatedCand
			gen, status, price               sql.NullString
			words, clicks, favs, praises     sql.NullInt64
			cover                            sql.NullString
			score                            sql.NullFloat64
		)
		if err := rows.Scan(&c.item.NID, &c.item.Title, &c.item.Author, &gen,
			&c.item.EstYear, &status, &price, &words, &clicks, &favs, &praises,
			&c.item.Form, &cover, &score, &c.ovl); err != nil {
			return nil, err
		}
		// cqs=NULL 的书照常入选（指标不进候选）；展示排序时 score=0 垫底。
		c.score = score.Float64
		c.item.Genre = strPtr(gen)
		c.item.Status = strPtr(status)
		c.item.PriceType = strPtr(price)
		c.item.Words = intPtr(words)
		c.item.Clicks = intPtr(clicks)
		c.item.Favs = intPtr(favs)
		c.item.Praises = intPtr(praises)
		c.item.CoverURL = strPtr(cover)
		out = append(out, c)
	}
	return out, rows.Err()
}

// relatedHits 一次批量查询取回每个候选命中的锚点强标签（分层与轮流都要用）。
func (s *Store) relatedHits(ctx context.Context, strong []string, cands []relatedCand) error {
	if len(strong) == 0 || len(cands) == 0 {
		return nil
	}
	ids := make([]string, len(cands))
	args := make([]any, 0, len(cands)+len(strong))
	at := map[int64]int{}
	for i := range cands {
		ids[i] = "?"
		args = append(args, cands[i].item.NID)
		at[cands[i].item.NID] = i
	}
	for _, t := range strong {
		args = append(args, t)
	}
	strongPh := strings.TrimSuffix(strings.Repeat("?,", len(strong)), ",")
	rows, err := s.DB.QueryContext(ctx, fmt.Sprintf(`
SELECT bt.nid, bt.tag FROM seed.book_tags bt
WHERE bt.nid IN (%s) AND bt.tag IN (%s)`, strings.Join(ids, ","), strongPh), args...)
	if err != nil {
		return err
	}
	defer rows.Close()
	for rows.Next() {
		var nid int64
		var tag string
		if err := rows.Scan(&nid, &tag); err != nil {
			return err
		}
		if i, ok := at[nid]; ok {
			cands[i].hits = append(cands[i].hits, tag)
		}
	}
	return rows.Err()
}

// sortRelatedStrata 实现 docs §3.5 的档内三步（全是内容信号）：
// 1) 候选归入其命中的最稀有强标签组（df ASC 整组靠前）；
// 2) 多个强标签轮流各出一本再循环，不让单一卖点占满；
// 3) 组内保持 SQL 的内容粗排序（重叠数 DESC、年代接近、nid ASC）。
// 自定义指标不进这里；它只在 RelatedBooks 选满后决定展示顺序（v5）。
func sortRelatedStrata(df map[string]int, cands []relatedCand) {
	groups := map[string][]relatedCand{}
	keys := []string{}
	for _, c := range cands {
		key, best := "", 1<<30
		for _, t := range c.hits {
			if d := df[t]; d < best {
				best, key = d, t
			}
		}
		if key == "" {
			continue
		}
		if _, ok := groups[key]; !ok {
			keys = append(keys, key)
		}
		groups[key] = append(groups[key], c)
	}
	sort.SliceStable(keys, func(i, j int) bool {
		if df[keys[i]] != df[keys[j]] {
			return df[keys[i]] < df[keys[j]]
		}
		return keys[i] < keys[j]
	})
	out := make([]relatedCand, 0, len(cands))
	for round := 0; ; round++ {
		alive := false
		for _, k := range keys {
			if round < len(groups[k]) {
				out = append(out, groups[k][round])
				alive = true
			}
		}
		if !alive {
			break
		}
	}
	// 无强标签命中的候选（降档前不该出现，防御）保持原序垫底。
	for _, c := range cands {
		if len(c.hits) == 0 {
			out = append(out, c)
		}
	}
	copy(cands, out)
}

// tagDF 返回锚点标签的全库书数（强标签判定与分层稀有度都用它）。
func (s *Store) tagDF(ctx context.Context, tags []string) (map[string]int, error) {
	out := map[string]int{}
	if len(tags) == 0 {
		return out, nil
	}
	args := make([]any, len(tags))
	ph := make([]string, len(tags))
	for i, t := range tags {
		args[i] = t
		ph[i] = "?"
	}
	rows, err := s.DB.QueryContext(ctx, fmt.Sprintf(`
SELECT tag, COUNT(*) FROM seed.book_tags WHERE tag IN (%s) GROUP BY tag`,
		strings.Join(ph, ",")), args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var t string
		var n int
		if err := rows.Scan(&t, &n); err != nil {
			return nil, err
		}
		out[t] = n
	}
	return out, rows.Err()
}

// isOperationalTag 认运营年份标签（2018萌神 …）：它们是活动标记，不是卖点。
func isOperationalTag(tag string) bool {
	return len(tag) >= 5 && strings.HasSuffix(tag, "萌神") &&
		tag[0] >= '0' && tag[0] <= '9'
}

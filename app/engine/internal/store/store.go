package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"

	"strata/engine/internal/appshell"

	_ "modernc.org/sqlite"
)

var ErrNotFound = errors.New("not found")

type Store struct {
	DB       *sql.DB
	Manifest *appshell.Manifest
	SeedPath string
	UserPath string
}

type Book struct {
	NID        int64    `json:"nid"`
	Title      string   `json:"title"`
	Author     string   `json:"author"`
	Genre      *string  `json:"genre"`
	PriceType  *string  `json:"price_type"`
	Status     *string  `json:"status"`
	Contest    *string  `json:"contest"`
	Words      *int64   `json:"words"`
	Clicks     *int64   `json:"clicks"`
	Favs       *int64   `json:"favs"`
	Praises    *int64   `json:"praises"`
	Featured   bool     `json:"featured"`
	CoverURL   *string  `json:"cover_url"`
	UpdatedAt  *string  `json:"updated_at"`
	EstYear    int      `json:"est_year"`
	EstDate    string   `json:"est_date"`
	EstConf    string   `json:"est_conf"`
	Tags       *string  `json:"tags"`
	PR         *float64 `json:"pr"`
	Form       string   `json:"form"`
	IsLicensed bool     `json:"is_licensed"`
}

type Observation struct {
	ObservedAt    int64   `json:"observed_at"`
	Clicks        *int64  `json:"clicks"`
	Favs          *int64  `json:"favs"`
	Praises       *int64  `json:"praises"`
	Words         *int64  `json:"words"`
	ShortComments *int64  `json:"short_comments"`
	LongComments  *int64  `json:"long_comments"`
	Status        *string `json:"status"`
	UpdatedAt     *string `json:"updated_at"`
	Source        string  `json:"source"`
}

// BookMeta is the latest metadata returned by one successful detail fetch.
// It is an overlay on the read-only seed; nil means "not returned, keep the
// previous value" (HTML and App API expose different subsets).
type BookMeta struct {
	NID         int64    `json:"nid"`
	Source      string   `json:"source"`
	FetchedAt   int64    `json:"fetched_at"`
	Title       *string  `json:"title"`
	Author      *string  `json:"author"`
	AuthorID    *int64   `json:"author_id"`
	Genre       *string  `json:"genre"`
	TypeID      *int64   `json:"type_id"`
	PriceType   *string  `json:"price_type"`
	Status      *string  `json:"status"`
	CoverURL    *string  `json:"cover_url"`
	Summary     *string  `json:"summary"`
	Words       *int64   `json:"words"`
	Favs        *int64   `json:"favs"`
	Praises     *int64   `json:"praises"`
	Clicks      *int64   `json:"clicks"`
	UpdatedAt   *string  `json:"updated_at"`
	AddTime     *string  `json:"add_time"`
	Point       *float64 `json:"point"`
	BgBanner    *string  `json:"bg_banner"`
	CategoryID  *int64   `json:"category_id"`
	IsSensitive *bool    `json:"is_sensitive"`
	AllowDown   *bool    `json:"allow_down"`
}

type BookDetail struct {
	Book  *Book        `json:"book"`
	Tags  []string     `json:"tags"`
	Local *Observation `json:"local"`
	Meta  *BookMeta    `json:"meta,omitempty"`
	// Awards are seed-side contest award rows (schema v5). Display-only
	// badge material; the field is omitted when the book has none.
	Awards []*Award `json:"awards,omitempty"`
}

// RefreshAttempt is the last user-triggered detail fetch for one nid.
type RefreshAttempt struct {
	NID         int64  `json:"nid"`
	AttemptedAt int64  `json:"attempted_at"`
	State       string `json:"state"`
}

// Open attaches the read-only seed DB to the writable user DB. SQLite ATTACH
// is per-connection, so the pool is limited to one connection.
func Open(userPath, seedPath string, manifest *appshell.Manifest) (*Store, error) {
	dsn := appshell.FileURI(userPath,
		"_pragma=busy_timeout(5000)"+
			"&_pragma=journal_mode(WAL)"+
			"&_pragma=synchronous(NORMAL)"+
			"&_pragma=foreign_keys(1)")
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)

	seedURI := appshell.FileURI(seedPath, "mode=ro")
	if _, err := db.Exec("ATTACH DATABASE ? AS seed", seedURI); err != nil {
		db.Close()
		return nil, fmt.Errorf("attach seed: %w", err)
	}

	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM seed.books").Scan(&count); err != nil {
		db.Close()
		return nil, fmt.Errorf("read seed: %w", err)
	}
	if count != manifest.BookCount {
		db.Close()
		return nil, fmt.Errorf("seed book_count %d != manifest %d", count, manifest.BookCount)
	}

	return &Store{
		DB:       db,
		Manifest: manifest,
		SeedPath: seedPath,
		UserPath: userPath,
	}, nil
}

func (s *Store) Close() error {
	if s == nil || s.DB == nil {
		return nil
	}
	return s.DB.Close()
}

func (s *Store) SeedMeta(ctx context.Context) (map[string]string, error) {
	rows, err := s.DB.QueryContext(ctx, "SELECT key, value FROM seed.seed_meta")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	meta := map[string]string{}
	for rows.Next() {
		var key, value string
		if err := rows.Scan(&key, &value); err != nil {
			return nil, err
		}
		meta[key] = value
	}
	return meta, rows.Err()
}

func (s *Store) Book(ctx context.Context, nid int64) (*BookDetail, error) {
	const q = `
SELECT nid, title, author, genre, price_type, status, contest, words, clicks,
       favs, praises, featured, cover_url, updated_at, est_year, est_date,
       est_conf, tags, pr, form,
       is_licensed
FROM seed.books WHERE nid = ?`

	var (
		b                                        Book
		genre, priceType, status, contest, cover sql.NullString
		words, clicks, favs, praises, featured   sql.NullInt64
		updatedAt, tags                          sql.NullString
		pr                                       sql.NullFloat64
		form                                     string
		isLicensed                               sql.NullInt64
	)
	err := s.DB.QueryRowContext(ctx, q, nid).Scan(
		&b.NID, &b.Title, &b.Author, &genre, &priceType, &status, &contest,
		&words, &clicks, &favs, &praises, &featured, &cover, &updatedAt,
		&b.EstYear, &b.EstDate, &b.EstConf, &tags,
		&pr, &form, &isLicensed,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	if err != nil {
		return nil, err
	}
	b.Genre = strPtr(genre)
	b.PriceType = strPtr(priceType)
	b.Status = strPtr(status)
	b.Contest = contestPtr(contest)
	b.Words = intPtr(words)
	b.Clicks = intPtr(clicks)
	b.Favs = intPtr(favs)
	b.Praises = intPtr(praises)
	b.Featured = featured.Valid && featured.Int64 != 0
	b.CoverURL = strPtr(cover)
	b.UpdatedAt = strPtr(updatedAt)
	b.Tags = strPtr(tags)
	b.PR = floatPtr(pr)
	b.Form = form
	b.IsLicensed = isLicensed.Valid && isLicensed.Int64 != 0

	tagList, err := s.bookTags(ctx, nid)
	if err != nil {
		return nil, err
	}
	local, err := s.latestObservation(ctx, nid)
	if err != nil {
		return nil, err
	}
	meta, err := s.BookMeta(ctx, nid)
	if err != nil {
		return nil, err
	}
	awards, err := s.BookAwards(ctx, nid)
	if err != nil {
		return nil, err
	}
	return &BookDetail{Book: &b, Tags: tagList, Local: local, Meta: meta,
		Awards: awards}, nil
}

func (s *Store) bookTags(ctx context.Context, nid int64) ([]string, error) {
	rows, err := s.DB.QueryContext(ctx,
		"SELECT tag FROM seed.book_tags WHERE nid = ? ORDER BY tag", nid)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	tags := []string{}
	for rows.Next() {
		var tag string
		if err := rows.Scan(&tag); err != nil {
			return nil, err
		}
		tags = append(tags, tag)
	}
	return tags, rows.Err()
}

func (s *Store) latestObservation(ctx context.Context, nid int64) (*Observation, error) {
	const q = `
SELECT observed_at, clicks, favs, praises, words, short_comments, long_comments,
       status, updated_at, source
FROM main.observations
WHERE nid = ?
ORDER BY observed_at DESC
LIMIT 1`
	var (
		o                                           Observation
		clicks, favs, praises, words, shortC, longC sql.NullInt64
		status, updatedAt                           sql.NullString
	)
	err := s.DB.QueryRowContext(ctx, q, nid).Scan(
		&o.ObservedAt, &clicks, &favs, &praises, &words, &shortC, &longC,
		&status, &updatedAt, &o.Source,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	o.Clicks = intPtr(clicks)
	o.Favs = intPtr(favs)
	o.Praises = intPtr(praises)
	o.Words = intPtr(words)
	o.ShortComments = intPtr(shortC)
	o.LongComments = intPtr(longC)
	o.Status = strPtr(status)
	o.UpdatedAt = strPtr(updatedAt)
	return &o, nil
}

type RankItem struct {
	Rank     int      `json:"rank"`
	NID      int64    `json:"nid"`
	Title    string   `json:"title"`
	Author   string   `json:"author"`
	Genre    *string  `json:"genre"`
	EstYear  int      `json:"est_year"`
	EstDate  *string  `json:"est_date,omitempty"`
	Favs     *int64   `json:"favs"`
	CQS      *float64 `json:"cqs,omitempty"`
	CQSState string   `json:"cqs_state,omitempty"`
	Contest  *string  `json:"contest"`
	CoverURL *string  `json:"cover_url"`
	Status   *string  `json:"status"`
	Words    *int64   `json:"words"`
	Clicks   *int64   `json:"clicks"`
	Praises  *int64   `json:"praises"`
	Form     string   `json:"form"`
	Tags     []string `json:"tags"`
}

func (s *Store) RankingFavs(ctx context.Context, year int, genre, status, contest string, limit int) ([]RankItem, error) {
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.favs, seed.books.contest,
       seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE est_year = ? AND is_licensed = 0`
	args := []any{year}
	if genre != "" {
		query += " AND genre = ?"
		args = append(args, genre)
	}
	if status != "" {
		query += " AND status = ?"
		args = append(args, status)
	}
	if contest != "" {
		// contest=1 means "any contest entry"; any other value (normalized
		// at the API layer) matches the event or any of its divisions.
		if contest == "1" {
			query += " AND contest != ''"
		} else {
			clause, ca := contestMatchClause("contest", contest)
			query += " AND " + clause
			args = append(args, ca...)
		}
	}
	query += " ORDER BY seed.books.favs DESC, seed.books.nid ASC LIMIT ?"
	args = append(args, limit)

	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item    RankItem
			gen     sql.NullString
			favs    sql.NullInt64
			contest sql.NullString
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs, &contest, &item.Form, &item.CoverURL); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		item.Contest = contestPtr(contest)
		items = append(items, item)
	}
	return items, rows.Err()
}

// ClassicBooks is the data-only browse list used by the Classic category,
// status and contest pages. It intentionally sorts by absolute favs, not by
// same-generation percentiles: Classic mode mirrors novly's cumulative view
// and has no quantitative layer.
func (s *Store) ClassicBooks(ctx context.Context, genre, status, contest, form, wordsBand, ptype string,
	tags []string, year, limit, offset int, order, dir string) ([]RankItem, error) {
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.praises, seed.books.contest, seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE seed.books.is_licensed = 0`
	args := []any{}
	if genre != "" {
		query += " AND seed.books.genre = ?"
		args = append(args, genre)
	}
	if status != "" {
		query += " AND seed.books.status = ?"
		args = append(args, status)
	}
	if contest != "" {
		if contest == "1" {
			query += " AND seed.books.contest != ''"
		} else {
			clause, ca := contestMatchClause("seed.books.contest", contest)
			query += " AND " + clause
			args = append(args, ca...)
		}
	}
	if form != "" {
		query += " AND seed.books.form = ?"
		args = append(args, form)
	}
	switch wordsBand {
	case "":
	case "short":
		query += " AND seed.books.words <= 50000"
	case "medium":
		query += " AND seed.books.words > 50000 AND seed.books.words <= 150000"
	case "long":
		query += " AND seed.books.words > 150000"
	default:
		return nil, fmt.Errorf("unsupported words band %q", wordsBand)
	}
	if year > 0 {
		query += " AND seed.books.est_year = ?"
		args = append(args, year)
	}
	if ptype != "" {
		query += " AND seed.books.price_type = ?"
		args = append(args, ptype)
	}
	if len(tags) > 0 {
		// 多值 = OR（用户 2026-11-21：筛选面板标签多选，命中任一即入）。
		ph := make([]string, len(tags))
		targs := make([]any, len(tags))
		for i, tg := range tags {
			ph[i] = "?"
			targs[i] = tg
		}
		query += " AND EXISTS (SELECT 1 FROM seed.book_tags t WHERE t.nid = seed.books.nid AND t.tag IN (" + strings.Join(ph, ",") + "))"
		args = append(args, targs...)
	}
	switch order {
	case "clicks", "praises", "words":
		// 经典榜（平台累计值，展示层，docs/12）：次级键 favs 保证平局
		// 可复现；dir=asc 为逆序（用户 2026-11-21），NULL 仍排末尾
		// （NULLS LAST，SQLite ≥3.30，本驱动 3.54）。
		if dir == "asc" {
			query += " ORDER BY seed.books." + order + " ASC NULLS LAST, seed.books.favs DESC, seed.books.nid ASC LIMIT ? OFFSET ?"
		} else {
			query += " ORDER BY seed.books." + order + " DESC, seed.books.favs DESC, seed.books.nid ASC LIMIT ? OFFSET ?"
		}
	default:
		// 收藏榜（默认 order）同样支持逆序。
		if dir == "asc" {
			query += " ORDER BY seed.books.favs ASC NULLS LAST, seed.books.nid ASC LIMIT ? OFFSET ?"
		} else {
			query += " ORDER BY seed.books.favs DESC, seed.books.nid ASC LIMIT ? OFFSET ?"
		}
	}
	args = append(args, limit, offset)

	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item                         RankItem
			gen, status, contest, cover  sql.NullString
			words, clicks, favs, praises sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &praises,
			&contest, &item.Form, &cover); err != nil {
			return nil, err
		}
		item.Rank = len(items) + offset + 1
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.Praises = intPtr(praises)
		item.Contest = contestPtr(contest)
		item.CoverURL = strPtr(cover)
		items = append(items, item)
	}
	return items, rows.Err()
}

type DeepRankItem struct {
	Rank    int      `json:"rank"`
	NID     int64    `json:"nid"`
	Title   string   `json:"title"`
	Author  string   `json:"author"`
	Genre   *string  `json:"genre"`
	EstYear int      `json:"est_year"`
	Value   *float64 `json:"value"`
	Pctl    *float64 `json:"pctl"`
	InSeed  bool     `json:"in_seed"`
}

// RankingDeep reads the additive D2 table. The candidate pool is the full
// statistical universe at build time, not the curated seed book list. Depth is
// the actual board size (min(200, eligible books)); it is returned so the UI can
// show a honest "N of M" instead of pretending every board has 200 entries.
// in_seed marks whether the nid is in the curated books table: the UI uses it
// to route taps to the detail page only for seed books (others currently 404).
func (s *Store) RankingDeep(ctx context.Context, year int, metric string, limit int) ([]DeepRankItem, int, error) {
	const q = `
SELECT d.rank_no, d.nid, d.title, d.author, d.genre, d.est_year, d.value, d.pctl,
       COUNT(*) OVER() AS board_depth,
       CASE WHEN b.nid IS NULL THEN 0 ELSE 1 END AS in_seed
FROM seed.deep_ranks d
LEFT JOIN seed.books b ON b.nid = d.nid
WHERE d.est_year = ? AND d.metric = ?
ORDER BY d.rank_no ASC LIMIT ?`
	rows, err := s.DB.QueryContext(ctx, q, year, metric, limit)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	items := make([]DeepRankItem, 0, limit)
	depth := 0
	for rows.Next() {
		var (
			item   DeepRankItem
			gen    sql.NullString
			value  sql.NullFloat64
			pctl   sql.NullFloat64
			inSeed int
		)
		if err := rows.Scan(&item.Rank, &item.NID, &item.Title, &item.Author,
			&gen, &item.EstYear, &value, &pctl, &depth, &inSeed); err != nil {
			return nil, 0, err
		}
		item.Genre = strPtr(gen)
		item.Value = floatPtr(value)
		item.Pctl = floatPtr(pctl)
		item.InSeed = inSeed != 0
		items = append(items, item)
	}
	return items, depth, rows.Err()
}

type ShortItem struct {
	Rank     int     `json:"rank"`
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	Genre    *string `json:"genre"`
	EstYear  int     `json:"est_year"`
	Favs     *int64  `json:"favs"`
	Words    *int64  `json:"words"`
	CoverURL *string `json:"cover_url"`
}

func (s *Store) RankingShort(ctx context.Context, limit int) ([]ShortItem, error) {
	const q = `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.favs, seed.books.words,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE words <= 50000 AND status = '已完结' AND is_licensed = 0
ORDER BY favs DESC, seed.books.nid ASC
LIMIT ?`
	rows, err := s.DB.QueryContext(ctx, q, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]ShortItem, 0, limit)
	for rows.Next() {
		var (
			item  ShortItem
			gen   sql.NullString
			favs  sql.NullInt64
			words sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs, &words, &item.CoverURL); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		item.Words = intPtr(words)
		items = append(items, item)
	}
	return items, rows.Err()
}

// boardKind maps the Classic board selector to its ordering column.
// All are platform cumulative values (docs/12 §1 novly showcase column).
func boardKindCol(kind string) (string, bool) {
	switch kind {
	case "recommend":
		return "praises DESC", true
	case "popular":
		return "clicks DESC", true
	case "favs":
		return "favs DESC", true
	case "new":
		return "est_date DESC", true
	case "finish":
		return "favs DESC", true // filtered to finished, still by favs
	case "words":
		return "words DESC", true
	}
	return "", false
}

// BoardBooks is the Classic full-catalog board (docs/12 showcase): platform
// cumulative values, no percentile math. Isolated from the recommendation
// signal whitelist — display only.
func (s *Store) BoardBooks(ctx context.Context, kind, form string, year, limit, offset int) ([]RankItem, error) {
	col, ok := boardKindCol(kind)
	if !ok {
		return nil, nil
	}
	q := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE is_licensed = 0`
	args := []any{}
	if form != "" {
		q += " AND seed.books.form = ?"
		args = append(args, form)
	}
	if year > 0 {
		q += " AND seed.books.est_year = ?"
		args = append(args, year)
	}
	if kind == "finish" {
		q += " AND status = '已完结'"
	}
	q += fmt.Sprintf(" ORDER BY %s LIMIT ? OFFSET ?", col)
	args = append(args, limit, offset)

	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item                RankItem
			gen, status, cover  sql.NullString
			words, clicks, favs sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &item.Form, &cover); err != nil {
			return nil, err
		}
		item.Rank = len(items) + offset + 1
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.CoverURL = strPtr(cover)
		items = append(items, item)
	}
	return items, rows.Err()
}

// Discover is the classic discovery stream: cover-bearing unlicensed books
// ordered by platform clicks (docs/12 §5: cover is a hard gate), keyset
// paginated by (clicks, nid) for stable, overlap-free infinite scrolling.
// cursor "" starts at the top; otherwise "clicks:nid" of the last item.
func (s *Store) Discover(ctx context.Context, cursor, form string, limit int) ([]RankItem, error) {
	q := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE is_licensed = 0 AND COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) IS NOT NULL`
	args := []any{}
	if form != "" {
		q += " AND seed.books.form = ?"
		args = append(args, form)
	}
	if cursor != "" {
		var clicks int64
		var nid int64
		if _, err := fmt.Sscanf(cursor, "%d:%d", &clicks, &nid); err != nil {
			return nil, err
		}
		q += " AND (clicks < ? OR (clicks = ? AND nid > ?))"
		args = append(args, clicks, clicks, nid)
	}
	q += " ORDER BY clicks DESC, seed.books.nid ASC LIMIT ?"
	args = append(args, limit)

	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item                RankItem
			gen, status, cover  sql.NullString
			words, clicks, favs sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &item.Form, &cover); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.CoverURL = strPtr(cover)
		items = append(items, item)
	}
	return items, rows.Err()
}

// Recommend is the classic fallback stream (docs/12 §3, E.30): ordering by
// pr DESC (the praises/favs ratio — device-recomputable, never a raw
// cumulative), then nid for a stable tie-break. Keyset cursor "0|pr|nid"
// — the leading zero is the retired lqs slot, kept so the 3-segment
// cursor grammar stays parseable. OFFSET is not used.
//
// Hard gates: is_licensed = 0, cover-bearing, pr NOT NULL (favs ≥ 10 —
// the same evidence proxy the retired fav_pctl gate provided). Raw
// cumulative values (clicks/favs/praises) ride along as display fields
// only — they never appear in ORDER BY (docs/12 §3.2 red line).
func (s *Store) Recommend(ctx context.Context, cursor, form string, limit int) ([]RankItem, string, error) {
	q := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.form, seed.books.pr,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE is_licensed = 0
  AND COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) IS NOT NULL
  AND seed.books.pr IS NOT NULL`
	args := []any{}
	if form != "" {
		q += " AND seed.books.form = ?"
		args = append(args, form)
	}
	if cursor != "" {
		pr, nid, err := parseRecommendCursor(cursor)
		if err != nil {
			return nil, "", err
		}
		q += ` AND (seed.books.pr < ?
  OR (seed.books.pr = ? AND seed.books.nid > ?))`
		args = append(args, pr, pr, nid)
	}
	q += ` ORDER BY seed.books.pr DESC, seed.books.nid ASC LIMIT ?`
	args = append(args, limit)

	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	var lastPr float64
	var lastNID int64
	for rows.Next() {
		var (
			item                RankItem
			gen, status, cover  sql.NullString
			words, clicks, favs sql.NullInt64
			pr                  sql.NullFloat64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &item.Form,
			&pr, &cover); err != nil {
			return nil, "", err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.CoverURL = strPtr(cover)
		lastPr = pr.Float64
		lastNID = item.NID
		items = append(items, item)
	}
	next := ""
	if len(items) == limit {
		next = RecommendCursor(lastPr, lastNID)
	}
	return items, next, rows.Err()
}

// RecommendCQS is the quantitative recommendation stream scored by the
// runtime quality metric cqs (app/docs/18-runtime-metrics.md, report 24):
// form-isolated, candidates restricted to the form's cps mid-band (20–80
// percentile — screening only, never a board), ordered by cqs — or by clx
// (cqs × (1−K+K×len_norm)) when k > 0, the user's 篇幅偏好 view computed
// at runtime and never stored. Keyset cursor "score|nid"; OFFSET is not
// used. Cumulative display fields (clicks/favs/praises) ride along
// read-only and never enter ORDER BY / WHERE (docs/12 §3.2 red line).
func (s *Store) RecommendCQS(ctx context.Context, cursor, form string, k float64, limit int) ([]RankItem, string, error) {
	lo, hi, ok := s.cpsMidBand(ctx, form)
	if !ok {
		return []RankItem{}, "", nil
	}
	seedScore := "seed.books.cqs"
	discScore := "discovered.cqs"
	if k > 0 {
		seedScore = fmt.Sprintf(
			"seed.books.cqs * (1 - %.17g + %.17g * COALESCE(seed.books.len_norm, 0))",
			k, k)
		discScore = fmt.Sprintf(
			"discovered.cqs * (1 - %.17g + %.17g * COALESCE(discovered.len_norm, 0))",
			k, k)
	}
	// Phase 2: score discovered rows that gained detail numbers, then fold
	// them into the same stream (app/docs/18-runtime-metrics.md P2). The
	// cps mid-band bounds come from the seed's own per-form percentiles.
	if err := s.scorePendingDiscovered(ctx); err != nil {
		return nil, "", err
	}
	q := `SELECT * FROM (
  SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
         seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
         seed.books.favs, seed.books.form,
         seed.books.cqs, seed.books.cqs_state,
         (` + seedScore + `) AS stream_score,
         COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
  FROM seed.books
  LEFT JOIN covers c ON c.nid = seed.books.nid
  WHERE is_licensed = 0
    AND COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) IS NOT NULL
    AND seed.books.form = ?
    AND seed.books.cqs IS NOT NULL
    AND seed.books.cps BETWEEN ? AND ?
  UNION ALL
  SELECT discovered.nid, discovered.title, discovered.author, discovered.genre,
         discovered.est_year, NULL, discovered.words, NULL,
         discovered.favs, discovered.form,
         discovered.cqs, discovered.cqs_state,
         (` + discScore + `) AS stream_score,
         COALESCE(c.cover, NULLIF(discovered.cover_url, '')) AS cover_url
  FROM discovered
  LEFT JOIN covers c ON c.nid = discovered.nid
  WHERE COALESCE(c.cover, NULLIF(discovered.cover_url, '')) IS NOT NULL
    AND discovered.form = ?
    AND discovered.cqs IS NOT NULL
    AND discovered.cps BETWEEN ? AND ?)
WHERE `
	args := []any{form, lo, hi, form, lo, hi}
	if cursor != "" {
		score, nid, err := parseScoreCursor(cursor)
		if err != nil {
			return nil, "", err
		}
		q += "stream_score < ? OR (stream_score = ? AND nid < ?)"
		args = append(args, score, score, nid)
	} else {
		q += "1 = 1"
	}
	q += " ORDER BY stream_score DESC, nid ASC LIMIT ?"
	args = append(args, limit)

	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	var lastScore *float64
	var lastNID int64
	for rows.Next() {
		var (
			item                RankItem
			gen, status, cover  sql.NullString
			words, clicks, favs sql.NullInt64
			cqs, score          sql.NullFloat64
			state               sql.NullString
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &item.Form,
			&cqs, &state, &score, &cover); err != nil {
			return nil, "", err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.CoverURL = strPtr(cover)
		item.CQS = floatPtr(cqs)
		item.CQSState = state.String
		items = append(items, item)
		if score.Valid {
			lastScore = &score.Float64
		}
		lastNID = item.NID
	}
	if err := rows.Err(); err != nil {
		return nil, "", err
	}
	var next string
	if len(items) == limit && lastScore != nil {
		next = strconv.FormatFloat(*lastScore, 'g', -1, 64) + "|" +
			strconv.FormatInt(lastNID, 10)
	}
	return items, next, nil
}

// cpsMidBand returns the form's cps 20–80 percentile bounds (the candidate
// screen of report 24 §2.2); ok=false when the form has too few scored rows
// for a meaningful band.
func (s *Store) cpsMidBand(ctx context.Context, form string) (lo, hi float64, ok bool) {
	var n int
	if err := s.DB.QueryRowContext(ctx,
		"SELECT COUNT(*) FROM seed.books WHERE form = ? AND cps IS NOT NULL",
		form).Scan(&n); err != nil || n < 5 {
		return 0, 0, false
	}
	off := int(float64(n) * 0.20)
	if err := s.DB.QueryRowContext(ctx,
		"SELECT cps FROM seed.books WHERE form = ? AND cps IS NOT NULL"+
			" ORDER BY cps LIMIT 1 OFFSET ?", form, off).Scan(&lo); err != nil {
		return 0, 0, false
	}
	if err := s.DB.QueryRowContext(ctx,
		"SELECT cps FROM seed.books WHERE form = ? AND cps IS NOT NULL"+
			" ORDER BY cps DESC LIMIT 1 OFFSET ?", form, off).Scan(&hi); err != nil {
		return 0, 0, false
	}
	return lo, hi, true
}

// parseScoreCursor decodes the "score|nid" keyset cursor of the cqs/clx
// stream. cqs is a signed log-scale score, not a percentile — NaN is
// rejected by self-comparison (NaN != NaN).
func parseScoreCursor(cursor string) (float64, int64, error) {
	parts := strings.Split(cursor, "|")
	if len(parts) != 2 {
		return 0, 0, fmt.Errorf("invalid recommend cursor %q", cursor)
	}
	score, err := strconv.ParseFloat(parts[0], 64)
	if err != nil || score != score {
		return 0, 0, fmt.Errorf("invalid score in recommend cursor %q", cursor)
	}
	nid, err := strconv.ParseInt(parts[1], 10, 64)
	if err != nil || nid <= 0 {
		return 0, 0, fmt.Errorf("invalid nid in recommend cursor %q", cursor)
	}
	return score, nid, nil
}

// RecommendCursor encodes (pr, nid) as the keyset cursor for Recommend;
// parseRecommendCursor is the inverse. The output keeps the legacy
// 3-segment grammar "0|pr|nid" — the leading zero is the retired lqs
// slot. Floats are formatted with minimal full precision so the round
// trip is exact.
func RecommendCursor(pr float64, nid int64) string {
	return "0|" + strconv.FormatFloat(pr, 'g', -1, 64) + "|" +
		strconv.FormatInt(nid, 10)
}

// parseRecommendCursor decodes the "0|pr|nid" keyset cursor. The first
// segment is the retired lqs slot: it must be empty or "0" (both parse,
// so cursors minted by older builds keep working); its value is
// otherwise ignored. pr is a ratio, not a percentile: unbounded above,
// and legitimately 0 (praises 0 with favs ≥ 10).
func parseRecommendCursor(cursor string) (float64, int64, error) {
	parts := strings.Split(cursor, "|")
	if len(parts) != 3 {
		return 0, 0, fmt.Errorf("invalid recommend cursor %q", cursor)
	}
	if parts[0] != "" && parts[0] != "0" {
		return 0, 0, fmt.Errorf("legacy lqs cursor %q is no longer accepted", cursor)
	}
	pr, err := strconv.ParseFloat(parts[1], 64)
	if err != nil || pr < 0 {
		return 0, 0, fmt.Errorf("invalid pr in recommend cursor %q", cursor)
	}
	nid, err := strconv.ParseInt(parts[2], 10, 64)
	if err != nil || nid <= 0 {
		return 0, 0, fmt.Errorf("invalid nid in recommend cursor %q", cursor)
	}
	return pr, nid, nil
}

// WatchlistCap is the hard watchlist size limit (docs/07 §1: 上限 100 本、
// 超限提示移除不自动删). self ≤20 / peer ≤80 是建议值，不强制。
const WatchlistCap = 100

// ErrWatchlistFull: 满员时拒绝新条目（重复加入不受限——幂等 no-op）。
var ErrWatchlistFull = errors.New("watchlist is full (cap 100); remove an entry first")

func validWatchRole(role string) bool { return role == "self" || role == "peer" }

// WatchAdd puts a book on the watchlist (v6: the single user-interest
// list). active=true tracks (background polling, former watchlist);
// active=false saves only (former bookshelf); role = self（本人作品）|
// peer（同期对照，docs/07 §1）。Idempotent — an existing entry keeps its
// state (INSERT OR IGNORE); the cap only blocks genuinely new entries.
func (s *Store) WatchAdd(ctx context.Context, nid int64, addedAt int64,
	active bool, role string) error {
	if !validWatchRole(role) {
		return fmt.Errorf("invalid watchlist role %q (want 'self' or 'peer')", role)
	}
	var count, exists int
	if err := s.DB.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM watchlist`).Scan(&count); err != nil {
		return err
	}
	if err := s.DB.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM watchlist WHERE nid = ?`, nid).Scan(&exists); err != nil {
		return err
	}
	if exists == 0 && count >= WatchlistCap {
		return ErrWatchlistFull
	}
	enabled := 0
	if active {
		enabled = 1
	}
	_, err := s.DB.ExecContext(ctx, `
INSERT OR IGNORE INTO watchlist(nid, role, added_at, poll_enabled) VALUES (?, ?, ?, ?)`,
		nid, role, addedAt, enabled)
	return err
}

// WatchSetRole switches an entry's role (docs/07 §1: role 可改，UPDATE 一
// 列，历史曲线连续). A missing nid is a no-op (same leniency as
// WatchSetActive).
func (s *Store) WatchSetRole(ctx context.Context, nid int64, role string) error {
	if !validWatchRole(role) {
		return fmt.Errorf("invalid watchlist role %q (want 'self' or 'peer')", role)
	}
	_, err := s.DB.ExecContext(ctx,
		`UPDATE watchlist SET role = ? WHERE nid = ?`, role, nid)
	return err
}

// WatchSetActive toggles tracking on a watchlist entry (v6): active
// entries poll in the background, inactive ones are save-only.
func (s *Store) WatchSetActive(ctx context.Context, nid int64, active bool) error {
	enabled := 0
	if active {
		enabled = 1
	}
	_, err := s.DB.ExecContext(ctx,
		`UPDATE watchlist SET poll_enabled = ? WHERE nid = ?`, enabled, nid)
	return err
}

// WatchRemove drops a book from the watchlist.
func (s *Store) WatchRemove(ctx context.Context, nid int64) error {
	_, err := s.DB.ExecContext(ctx, `DELETE FROM watchlist WHERE nid = ?`, nid)
	return err
}

// WatchItem is a watchlist row joined with seed metadata.
type WatchItem struct {
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	Genre    *string `json:"genre"`
	CoverURL *string `json:"cover_url"`
	AddedAt  int64   `json:"added_at"`
	Role     string  `json:"role"`
	Note     *string `json:"note"`
	// Active = tracking on (poll_enabled). Since v6 the watchlist is the
	// single user-interest list: active entries are tracked, inactive
	// ones are save-only (the former bookshelf).
	Active bool `json:"active"`
}

// WatchList joins the watchlist with seed metadata, newest first.
func (s *Store) WatchList(ctx context.Context) ([]WatchItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT w.nid,
       COALESCE(b.title, d.title, '') AS title,
       COALESCE(b.author, d.author, '') AS author,
       COALESCE(b.genre, d.genre),
       COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover_url,
       w.added_at, w.role, w.note, w.poll_enabled
FROM watchlist w
LEFT JOIN seed.books b ON b.nid = w.nid
LEFT JOIN discovered d ON d.nid = w.nid
LEFT JOIN covers c ON c.nid = w.nid
ORDER BY w.added_at DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []WatchItem{}
	for rows.Next() {
		var (
			it         WatchItem
			gen, cover sql.NullString
			note       sql.NullString
			poll       int
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &gen,
			&cover, &it.AddedAt, &it.Role, &note, &poll); err != nil {
			return nil, err
		}
		it.Genre = strPtr(gen)
		it.CoverURL = strPtr(cover)
		it.Note = strPtr(note)
		it.Active = poll == 1
		items = append(items, it)
	}
	return items, rows.Err()
}

// WatchDue returns nids whose poll schedule is due: poll enabled and
// (never polled or past poll_interval). Ordered oldest-last-poll first.
func (s *Store) WatchDue(ctx context.Context, now int64, limit int) ([]int64, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid FROM watchlist
WHERE poll_enabled = 1 AND (last_poll_at IS NULL OR ? - last_poll_at >= poll_interval)
ORDER BY last_poll_at ASC LIMIT ?`, now, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	nids := []int64{}
	for rows.Next() {
		var nid int64
		if err := rows.Scan(&nid); err != nil {
			return nil, err
		}
		nids = append(nids, nid)
	}
	return nids, rows.Err()
}

// WatchPollDone stamps the completion time of a scheduled poll.
func (s *Store) WatchPollDone(ctx context.Context, nid, at int64) error {
	_, err := s.DB.ExecContext(ctx,
		`UPDATE watchlist SET last_poll_at = ? WHERE nid = ?`, at, nid)
	return err
}

// RandomBooks samples n unlicensed seed books uniformly at random
// (ORDER BY RANDOM), used by the home "shuffle" grid. Cover and stats
// included so cards render identically to board items.
// megaBookMinWords: the home "随便看看" browse pool — big books only,
// regardless of whether they are ongoing or finished.
const megaBookMinWords = 600000

// RandomBooks samples n unlicensed seed books uniformly at random
// (ORDER BY RANDOM is a uniform permutation). status selects the pool:
// "" draws from the whole seed, "serial" from ongoing works, "finished"
// from completed works. "browse" (the home shuffle section) keeps the
// big-book gate only for the default long-form tab; shorter forms must not
// be filtered out by a size threshold. Every pool also honours the optional
// form filter. Any other status value is rejected.
func (s *Store) RandomBooks(ctx context.Context, limit int, status, form string) ([]RankItem, error) {
	var pool string
	switch status {
	case "":
		pool = ""
	case "serial":
		pool = " AND status = '连载中'"
	case "finished":
		pool = " AND status = '已完结'"
	case "browse":
		if form == "" || form == "long" {
			pool = " AND words >= " + strconv.Itoa(megaBookMinWords)
		}
	case "short":
		pool = "" // 短篇池：form=short 本身就是过滤，无字数门槛
	default:
		return nil, fmt.Errorf("unsupported random status %q", status)
	}
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.praises, seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE is_licensed = 0` + pool
	args := []any{}
	if form != "" {
		query += " AND seed.books.form = ?"
		args = append(args, form)
	}
	query += " ORDER BY RANDOM() LIMIT ?"
	args = append(args, limit)
	rows, err := s.DB.QueryContext(ctx, query, args...)
	return s.scanRankItems(ctx, rows, err)
}

// scanRankItems reads one result set of the shared seed-book query
// (RandomBooks / curated pools) and fills batched tags.
func (s *Store) scanRankItems(ctx context.Context, rows *sql.Rows,
	err error) ([]RankItem, error) {
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []RankItem{}
	for rows.Next() {
		var (
			item               RankItem
			gen, status, cover sql.NullString
			words, clicks, favs,
			praises sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &praises, &item.Form, &cover); err != nil {
			return nil, err
		}
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.Praises = intPtr(praises)
		item.CoverURL = strPtr(cover)
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	s.attachTags(ctx, items)
	return items, nil
}

// curated is the shared scan for the deterministic home pools: the same
// seed-book SELECT as RandomBooks, with a pool-specific WHERE clause and
// favs ordering (no randomness — these are small fixed lists).
func (s *Store) curated(ctx context.Context, limit int, extra string) ([]RankItem, error) {
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.praises, seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE 1=1` + extra +
		` ORDER BY seed.books.favs DESC, seed.books.nid ASC LIMIT ?`
	rows, err := s.DB.QueryContext(ctx, query, limit)
	return s.scanRankItems(ctx, rows, err)
}

// LicensedBooks lists the licensed Japanese light novels (is_licensed=1,
// 47 in the canonical seed): searchable and detail-visible, but excluded
// from every percentile pool.
func (s *Store) LicensedBooks(ctx context.Context, limit int) ([]RankItem, error) {
	return s.curated(ctx, limit, " AND seed.books.is_licensed = 1")
}

// MoeGoddessBooks lists books carrying a yearly 萌神 award tag
// (2018萌神 … 2024萌神, 2 per year in the canonical seed).
func (s *Store) MoeGoddessBooks(ctx context.Context, limit int) ([]RankItem, error) {
	return s.curated(ctx, limit,
		" AND seed.books.nid IN (SELECT nid FROM seed.book_tags "+
			"WHERE tag LIKE '____萌神')")
}

// AuthorBooks lists one author's seed books in timeline order (est_date
// DESC; manual-early backfill rows with est_date '0001-01-01' sink to
// the bottom) for the author page. Local seed data only — no network
// (docs/author-profile-on-demand §1: the works list is read from the
// local db). Seed author display names are canonical strings, so an
// exact match is the identity check.
func (s *Store) AuthorBooks(ctx context.Context, author string, limit, offset int, newestFirst bool) ([]RankItem, error) {
	// Backfilled books (est_date NULL/'' — the 0001 sentinel) stay at the
	// bottom in either direction.
	order := "ORDER BY CASE WHEN seed.books.est_date IS NULL OR seed.books.est_date = '' THEN 1 ELSE 0 END, seed.books.est_date DESC, seed.books.nid ASC"
	if !newestFirst {
		order = "ORDER BY CASE WHEN seed.books.est_date IS NULL OR seed.books.est_date = '' THEN 1 ELSE 0 END, seed.books.est_date ASC, seed.books.nid DESC"
	}
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.praises, seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url,
       seed.books.est_date
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE seed.books.author = ?
` + order + `
LIMIT ? OFFSET ?`
	rows, err := s.DB.QueryContext(ctx, query, author, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []RankItem{}
	for rows.Next() {
		var (
			item               RankItem
			edate              sql.NullString
			gen, status, cover sql.NullString
			words, clicks, favs,
			praises sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &praises,
			&item.Form, &cover, &edate); err != nil {
			return nil, err
		}
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.Praises = intPtr(praises)
		item.CoverURL = strPtr(cover)
		item.EstDate = strPtr(edate)
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	s.attachTags(ctx, items)
	return items, nil
}

// AuthorProfile is one cached on-demand author data row (user.db
// author_profiles, v7; docs/author-profile-on-demand §3-4). A snapshot:
// intro and avatar change with the author, so the row carries the fetch
// time (observed_at) and the source book (source_nid).
type AuthorProfile struct {
	AuthorKey    string
	AuthorName   string
	AuthorIntro  *string
	AuthorAvatar *string
	Verdict      string
	SourceNID    int64
	ObservedAt   int64
	// Works is the cached official works list as a JSON array (v8);
	// nil when never fetched or the verdict carries no works.
	Works *string
}

// SeedNIDSet reports which of the given nids are present in seed.books
// (author works-collection off-library diff, docs/author-profile-on-demand
// §6). The IN list is batched; the caller preserves page order, this only
// answers membership.
func (s *Store) SeedNIDSet(ctx context.Context, nids []int64) (map[int64]bool, error) {
	out := make(map[int64]bool, len(nids))
	const batch = 500
	for start := 0; start < len(nids); start += batch {
		end := start + batch
		if end > len(nids) {
			end = len(nids)
		}
		chunk := nids[start:end]
		ph := make([]string, len(chunk))
		args := make([]any, len(chunk))
		for i, n := range chunk {
			ph[i] = "?"
			args[i] = n
		}
		rows, err := s.DB.QueryContext(ctx,
			"SELECT nid FROM seed.books WHERE nid IN ("+
				strings.Join(ph, ",")+")", args...)
		if err != nil {
			return nil, err
		}
		for rows.Next() {
			var nid int64
			if err := rows.Scan(&nid); err != nil {
				rows.Close()
				return nil, err
			}
			out[nid] = true
		}
		rerr := rows.Err()
		rows.Close()
		if rerr != nil {
			return nil, rerr
		}
	}
	return out, nil
}

// GetAuthorProfile returns the cached row, or nil when the author was
// never fetched (or the row was evicted).
func (s *Store) GetAuthorProfile(ctx context.Context, key string) (*AuthorProfile, error) {
	var (
		p             AuthorProfile
		intro, avatar sql.NullString
		works         sql.NullString
	)
	err := s.DB.QueryRowContext(ctx, `
SELECT author_name, author_intro, author_avatar, verdict, source_nid, observed_at, works
FROM author_profiles WHERE author_key = ?`, key).
		Scan(&p.AuthorName, &intro, &avatar, &p.Verdict, &p.SourceNID, &p.ObservedAt, &works)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	p.AuthorKey = key
	p.AuthorIntro = strPtr(intro)
	p.Works = strPtr(works)
	p.AuthorAvatar = strPtr(avatar)
	return &p, nil
}

// SaveAuthorProfile upserts one cached profile.
func (s *Store) SaveAuthorProfile(ctx context.Context, p *AuthorProfile) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO author_profiles(author_key, author_name, author_intro, author_avatar,
                             verdict, source_nid, observed_at, works)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(author_key) DO UPDATE SET
  author_name = excluded.author_name,
  author_intro = excluded.author_intro,
  author_avatar = excluded.author_avatar,
  verdict = excluded.verdict,
  source_nid = excluded.source_nid,
  observed_at = excluded.observed_at,
  works = excluded.works`,
		p.AuthorKey, p.AuthorName, p.AuthorIntro, p.AuthorAvatar,
		p.Verdict, p.SourceNID, p.ObservedAt, p.Works)
	return err
}

// CoverCarousel returns one form's cover-bearing head pool, drawn with
// the daily date hash: the pool is the top 100 by favs among cover-
// bearing books of the form (quality floor — the dialogue long tail is
// mostly mediocre, user-confirmed 2026-11-19), and the displayed slice
// rotates daily with the same hash as BannerPick (B=500001 ≈ half the
// 1,000,003-bucket key space), so consecutive days show different books
// while staying within the head. Cover-less books are excluded up front,
// so the client always gets a drawable result.
func (s *Store) CoverCarousel(ctx context.Context, form string,
	limit int, seed int64) ([]RankItem, error) {
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.praises, seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE seed.books.nid IN (
  SELECT b.nid FROM seed.books b
  LEFT JOIN covers c2 ON c2.nid = b.nid
  WHERE b.form = ?
    AND COALESCE(c2.cover, b.cover_url) IS NOT NULL
    AND COALESCE(c2.cover, b.cover_url) != ''
  ORDER BY b.favs DESC, b.nid ASC
  LIMIT 100)
ORDER BY (seed.books.nid*2654435761 + ?*500001) % 1000003, seed.books.nid
LIMIT ?`
	rows, err := s.DB.QueryContext(ctx, query, form, seed, limit)
	return s.scanRankItems(ctx, rows, err)
}

// IpGroup is one contest (征文) cluster of an IP pool: the IP tab groups
// books by which IP they collab with, and in the seed that axis is the
// contest field (崩坏3征文 → 崩坏3, 少女前线征文 → 少女前线, …).
//
// TopNID/TopTitle/TopCover describe the group's favourite leader so the
// IP tab can render its text card without one /ip-books request per group.
type IpGroup struct {
	Contest  string `json:"contest"`
	Count    int    `json:"count"`
	TopNID   int64  `json:"top_nid"`
	TopTitle string `json:"top_title"`
	TopCover string `json:"top_cover"`
}

// IpGroups aggregates one form's books by contest for the IP tab's group
// grid: named IPs by count DESC (stable contest ASC tie-break) plus the
// pool total and each group's favourite leader for the card copy.
func (s *Store) IpGroups(ctx context.Context, form, status string) (int,
	[]IpGroup, error) {
	where := "WHERE form = ?"
	args := []any{form}
	if status != "" {
		where += " AND status = ?"
		args = append(args, status)
	}
	var total int
	if err := s.DB.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM seed.books `+where, args...).Scan(&total); err != nil {
		return 0, nil, err
	}
	rows, err := s.DB.QueryContext(ctx, `
SELECT contest, COUNT(*) AS c FROM seed.books
`+where+` AND contest IS NOT NULL AND contest != ''
GROUP BY contest ORDER BY c DESC, contest ASC`, args...)
	if err != nil {
		return 0, nil, err
	}
	defer rows.Close()
	groups := []IpGroup{}
	for rows.Next() {
		var g IpGroup
		if err := rows.Scan(&g.Contest, &g.Count); err != nil {
			return 0, nil, err
		}
		groups = append(groups, g)
	}
	if err := rows.Err(); err != nil {
		return 0, nil, err
	}
	merged := mergeContestGroups(groups)
	for i := range merged {
		nid, title, cover, err := s.ipGroupTopBook(ctx, form, status,
			merged[i].Contest)
		if err != nil {
			return 0, nil, err
		}
		merged[i].TopNID = nid
		merged[i].TopTitle = title
		merged[i].TopCover = cover
	}
	return total, merged, nil
}

// ipGroupTopBook returns the favourite leader of one merged contest group,
// matching every raw division spelling of an N届 event. Empty fields mean
// the group has no book (should not happen for a merged group).
func (s *Store) ipGroupTopBook(ctx context.Context, form, status,
	contest string) (int64, string, string, error) {
	where := "seed.books.form = ?"
	args := []any{form}
	if status != "" {
		where += " AND seed.books.status = ?"
		args = append(args, status)
	}
	clause, ca := contestMatchClause("seed.books.contest", contest)
	where += " AND " + clause
	args = append(args, ca...)
	var (
		nid   int64
		title string
		cover sql.NullString
	)
	err := s.DB.QueryRowContext(ctx, `
SELECT seed.books.nid, seed.books.title,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE `+where+`
ORDER BY seed.books.favs DESC, seed.books.nid ASC LIMIT 1`, args...).
		Scan(&nid, &title, &cover)
	if errors.Is(err, sql.ErrNoRows) {
		return 0, "", "", nil
	}
	if err != nil {
		return 0, "", "", err
	}
	return nid, title, cover.String, nil
}

// FacetValue is one selectable value of a filter dimension with its pool
// count (GET /strata/facets).
type FacetValue struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

// FacetYear is one est_year cohort facet (a number, not a name).
type FacetYear struct {
	Year  int `json:"year"`
	Count int `json:"count"`
}

// Facets is one form pool's filter facet lists for the classic-list filter
// sheet (user 2026-11-21): genres, price types, the top 60 tags and years,
// each with pool counts over the same is_licensed=0 pool the classic lists
// read. form "" means every form. No allow-lists: unknown values in
// /rankings/classic simply match nothing.
func (s *Store) Facets(ctx context.Context, form string) (
	genres, ptypes, tags []FacetValue, years []FacetYear, err error) {
	where := " WHERE seed.books.is_licensed = 0"
	args := []any{}
	if form != "" {
		where += " AND seed.books.form = ?"
		args = append(args, form)
	}
	count := func(column, extra string) ([]FacetValue, error) {
		rows, qerr := s.DB.QueryContext(ctx,
			"SELECT "+column+", COUNT(*) AS c FROM seed.books"+where+extra+
				" GROUP BY "+column+" ORDER BY c DESC, "+column+" ASC", args...)
		if qerr != nil {
			return nil, qerr
		}
		defer rows.Close()
		out := []FacetValue{}
		for rows.Next() {
			var v FacetValue
			if serr := rows.Scan(&v.Name, &v.Count); serr != nil {
				return nil, serr
			}
			out = append(out, v)
		}
		return out, rows.Err()
	}
	if genres, err = count("genre", " AND genre IS NOT NULL AND genre != ''"); err != nil {
		return
	}
	if ptypes, err = count("price_type", " AND price_type IS NOT NULL AND price_type != ''"); err != nil {
		return
	}
	tagWhere := " WHERE b.is_licensed = 0"
	tagArgs := []any{}
	if form != "" {
		tagWhere += " AND b.form = ?"
		tagArgs = append(tagArgs, form)
	}
	tagRows, terr := s.DB.QueryContext(ctx, `
SELECT t.tag, COUNT(*) AS c
FROM seed.book_tags t
JOIN seed.books b ON b.nid = t.nid`+tagWhere+`
GROUP BY t.tag ORDER BY c DESC, t.tag ASC LIMIT 60`, tagArgs...)
	if terr != nil {
		return
	}
	tags = []FacetValue{}
	for tagRows.Next() {
		var v FacetValue
		if serr := tagRows.Scan(&v.Name, &v.Count); serr != nil {
			tagRows.Close()
			return nil, nil, nil, nil, serr
		}
		tags = append(tags, v)
	}
	if serr := tagRows.Err(); serr != nil {
		tagRows.Close()
		return nil, nil, nil, nil, serr
	}
	tagRows.Close()
	yearRows, yerr := s.DB.QueryContext(ctx, `
SELECT est_year, COUNT(*) AS c FROM seed.books`+where+
		` AND est_year IS NOT NULL GROUP BY est_year ORDER BY est_year DESC`, args...)
	if yerr != nil {
		return
	}
	years = []FacetYear{}
	for yearRows.Next() {
		var y FacetYear
		if serr := yearRows.Scan(&y.Year, &y.Count); serr != nil {
			yearRows.Close()
			return nil, nil, nil, nil, serr
		}
		years = append(years, y)
	}
	if serr := yearRows.Err(); serr != nil {
		yearRows.Close()
		return nil, nil, nil, nil, serr
	}
	yearRows.Close()
	return
}

// YearGroup is one est_year cohort of a form pool: the short tab's year
// entry (books per year).
type YearGroup struct {
	Year  int `json:"year"`
	Count int `json:"count"`
}

// YearGroups aggregates one form's seed books by est_year (DESC) plus the
// pool total.
func (s *Store) YearGroups(ctx context.Context, form string) (int,
	[]YearGroup, error) {
	var total int
	if err := s.DB.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM seed.books WHERE form = ?`,
		form).Scan(&total); err != nil {
		return 0, nil, err
	}
	rows, err := s.DB.QueryContext(ctx, `
SELECT est_year, COUNT(*) AS c FROM seed.books
WHERE form = ?
GROUP BY est_year ORDER BY est_year DESC`, form)
	if err != nil {
		return 0, nil, err
	}
	defer rows.Close()
	groups := []YearGroup{}
	for rows.Next() {
		var g YearGroup
		if err := rows.Scan(&g.Year, &g.Count); err != nil {
			return 0, nil, err
		}
		groups = append(groups, g)
	}
	if err := rows.Err(); err != nil {
		return 0, nil, err
	}
	return total, groups, nil
}

// GenreGroup is one genre of a form pool: the short tab's genre browse
// entry (books per genre).
type GenreGroup struct {
	Genre string `json:"genre"`
	Count int    `json:"count"`
}

// GenreGroups aggregates one form's seed books by genre (count DESC, genre
// ASC tie-break) plus the pool total.
func (s *Store) GenreGroups(ctx context.Context, form string) (int,
	[]GenreGroup, error) {
	var total int
	if err := s.DB.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM seed.books WHERE form = ?`,
		form).Scan(&total); err != nil {
		return 0, nil, err
	}
	rows, err := s.DB.QueryContext(ctx, `
SELECT genre, COUNT(*) AS c FROM seed.books
WHERE form = ? AND genre IS NOT NULL AND genre != ''
GROUP BY genre ORDER BY c DESC, genre ASC`, form)
	if err != nil {
		return 0, nil, err
	}
	defer rows.Close()
	groups := []GenreGroup{}
	for rows.Next() {
		var g GenreGroup
		if err := rows.Scan(&g.Genre, &g.Count); err != nil {
			return 0, nil, err
		}
		groups = append(groups, g)
	}
	if err := rows.Err(); err != nil {
		return 0, nil, err
	}
	return total, groups, nil
}

// IpBooks lists one IP entry: group names a contest exactly, or
// "other" for the long tail outside the top-2 contests by count (the
// named entries). favs DESC within the group — the IP pool is small
// and stable, no randomness.
func (s *Store) IpBooks(ctx context.Context, form, group string,
	limit, offset int) ([]RankItem, error) {
	where := "seed.books.form = ?"
	args := []any{form}
	if group == "other" {
		// Top-2 events by merged (normalized) count: fetch every raw group,
		// fold divisions into events, keep the top-2 event names, then
		// exclude every raw spelling of those two events.
		rows, err := s.DB.QueryContext(ctx, `
SELECT contest, COUNT(*) AS c FROM seed.books
WHERE form = ? AND contest IS NOT NULL AND contest != ''
GROUP BY contest ORDER BY c DESC, contest ASC`, form)
		if err != nil {
			return nil, err
		}
		var names []string
		merged := map[string]int{}
		for rows.Next() {
			var c string
			var n int
			if err := rows.Scan(&c, &n); err != nil {
				rows.Close()
				return nil, err
			}
			name := NormalizeContest(c)
			if merged[name] == 0 {
				names = append(names, name)
			}
			merged[name] += n
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return nil, err
		}
		sort.Slice(names, func(i, j int) bool {
			if merged[names[i]] != merged[names[j]] {
				return merged[names[i]] > merged[names[j]]
			}
			return names[i] < names[j]
		})
		if len(names) > 2 {
			names = names[:2]
		}
		where += " AND contest IS NOT NULL AND contest != ''"
		if len(names) > 0 {
			ph := []string{}
			for _, name := range names {
				for _, v := range []string{name, name + "长篇", name + "中篇", name + "短篇"} {
					ph = append(ph, "?")
					args = append(args, v)
				}
			}
			where += fmt.Sprintf(" AND contest NOT IN (%s)", strings.Join(ph, ","))
		}
	} else {
		clause, ca := contestMatchClause("contest", group)
		where += " AND " + clause
		args = append(args, ca...)
	}
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author, seed.books.genre,
       seed.books.est_year, seed.books.status, seed.books.words, seed.books.clicks,
       seed.books.favs, seed.books.praises, seed.books.contest, seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE ` + where +
		` ORDER BY seed.books.favs DESC, seed.books.nid ASC LIMIT ? OFFSET ?`
	args = append(args, limit, offset)
	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	// 13-column scan (with contest — the client renders an IP badge from
	// it on mixed-IP lists); kept separate from scanRankItems, which
	// scans the 12-column shape shared by the other pools. Tags attached
	// as usual.
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item                         RankItem
			gen, status, contest, cover  sql.NullString
			words, clicks, favs, praises sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &status, &words, &clicks, &favs, &praises,
			&contest, &item.Form, &cover); err != nil {
			return nil, err
		}
		item.Rank = len(items) + offset + 1
		item.Genre = strPtr(gen)
		item.Status = strPtr(status)
		item.Words = intPtr(words)
		item.Clicks = intPtr(clicks)
		item.Favs = intPtr(favs)
		item.Praises = intPtr(praises)
		item.Contest = contestPtr(contest)
		item.CoverURL = strPtr(cover)
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	s.attachTags(ctx, items)
	return items, nil
}

// attachTags fills item.Tags from seed.book_tags with a single batched
// query (avoids N+1 for the random-serial page's 100 rows).
func (s *Store) attachTags(ctx context.Context, items []RankItem) {
	if len(items) == 0 {
		return
	}
	placeholders := make([]string, len(items))
	args := make([]any, len(items))
	for i, it := range items {
		placeholders[i] = "?"
		args[i] = it.NID
	}
	query := fmt.Sprintf(`
SELECT nid, tag FROM seed.book_tags WHERE nid IN (%s) ORDER BY tag`,
		strings.Join(placeholders, ","))
	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return
	}
	defer rows.Close()
	for rows.Next() {
		var (
			nid int64
			tag string
		)
		if err := rows.Scan(&nid, &tag); err != nil {
			return
		}
		for i := range items {
			if items[i].NID == nid {
				items[i].Tags = append(items[i].Tags, tag)
			}
		}
	}
}

// Search is the L1 local search over the bundled seed (title/author LIKE).
// Licensed books are included: they are searchable and detail-visible by
// design, just excluded from percentile rankings.
// parseNIDQuery decodes an exact nid search: an all-digit query of 4+ chars
// (SFACG nids are 4+ digits; 1–3 digit strings stay keyword search — a bare
// "7" is far more likely a word than an id). 0,false = keyword path.
func parseNIDQuery(q string) (int64, bool) {
	if len(q) < 4 {
		return 0, false
	}
	for i := 0; i < len(q); i++ {
		if q[i] < '0' || q[i] > '9' {
			return 0, false
		}
	}
	n, err := strconv.ParseInt(q, 10, 64)
	if err != nil {
		return 0, false
	}
	return n, true
}

func (s *Store) Search(ctx context.Context, q string, limit int) ([]SearchItem, error) {
	var (
		rows *sql.Rows
		err  error
	)
	if n, ok := parseNIDQuery(q); ok {
		// nid 精确（docs/08 §search）：种子 + 已收录并集，nid = q。
		rows, err = s.DB.QueryContext(ctx, `
SELECT nid, title, author, genre, est_year, favs, cover_url, in_seed FROM (
  SELECT b.nid AS nid, b.title AS title, b.author AS author, b.genre AS genre,
         b.est_year AS est_year, b.favs AS favs,
         COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover_url,
         1 AS in_seed
  FROM seed.books b
  LEFT JOIN covers c ON c.nid = b.nid
  WHERE b.nid = ?
  UNION ALL
  SELECT d.nid, d.title, d.author, d.genre, NULL, d.favs, d.cover_url, 0
  FROM discovered d
  WHERE d.nid = ?
)
ORDER BY in_seed DESC, nid ASC
LIMIT ?`, n, n, limit)
	} else {
		const esc = `\\`
		pattern := "%" + strings.NewReplacer("%", esc+"%", "_", esc+"_", "\\", esc+esc).Replace(q) + "%"
		rows, err = s.DB.QueryContext(ctx, `
SELECT nid, title, author, genre, est_year, favs, cover_url, in_seed FROM (
  SELECT b.nid AS nid, b.title AS title, b.author AS author, b.genre AS genre,
         b.est_year AS est_year, b.favs AS favs,
         COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover_url,
         1 AS in_seed
  FROM seed.books b
  LEFT JOIN covers c ON c.nid = b.nid
  WHERE (b.title LIKE ? ESCAPE '\' OR b.author LIKE ? ESCAPE '\')
  UNION ALL
  SELECT d.nid, d.title, d.author, d.genre, NULL, d.favs, d.cover_url, 0
  FROM discovered d
  WHERE (d.title LIKE ? ESCAPE '\' OR d.author LIKE ? ESCAPE '\')
)
ORDER BY favs DESC, nid ASC
LIMIT ?`, pattern, pattern, pattern, pattern, limit)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]SearchItem, 0, limit)
	for rows.Next() {
		var (
			item          SearchItem
			gen, cover    sql.NullString
			estYear, favs sql.NullInt64
			inSeed        int
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&estYear, &favs, &cover, &inSeed); err != nil {
			return nil, err
		}
		item.Genre = strPtr(gen)
		if estYear.Valid {
			item.EstYear = int(estYear.Int64)
		}
		item.Favs = intPtr(favs)
		item.CoverURL = strPtr(cover)
		item.InSeed = inSeed != 0
		items = append(items, item)
	}
	return items, rows.Err()
}

// AddSearchHistory records one local search (user.db search_history, the
// v5 table — no migration needed). Every submit is kept with its hit
// count; the retention pass trims the table to the newest 200 rows so
// it stays bounded without a unique-key upsert.
func (s *Store) AddSearchHistory(ctx context.Context, keyword string, hits int) error {
	if _, err := s.DB.ExecContext(ctx,
		`INSERT INTO search_history(keyword, at, hits) VALUES (?, ?, ?)`,
		keyword, time.Now().Unix(), hits); err != nil {
		return err
	}
	_, err := s.DB.ExecContext(ctx, `
DELETE FROM search_history WHERE id NOT IN
  (SELECT id FROM search_history ORDER BY at DESC, id DESC LIMIT 200)`)
	return err
}

// SearchHistory returns recent distinct keywords, most recently used
// first (search page empty state, docs/08 §search-history).
func (s *Store) SearchHistory(ctx context.Context, limit int) ([]string, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT keyword FROM (
  SELECT keyword, MAX(at) AS last_at, MAX(id) AS last_id
  FROM search_history GROUP BY keyword
) ORDER BY last_at DESC, last_id DESC LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []string{}
	for rows.Next() {
		var kw string
		if err := rows.Scan(&kw); err != nil {
			return nil, err
		}
		out = append(out, kw)
	}
	return out, rows.Err()
}

// SeedNIDsIn returns the subset of nids present in the bundled seed
// (official-search hits are marked in/out of the local library).
func (s *Store) SeedNIDsIn(ctx context.Context, nids []int64) (map[int64]bool, error) {
	out := make(map[int64]bool, len(nids))
	if len(nids) == 0 {
		return out, nil
	}
	args := make([]any, len(nids))
	placeholders := strings.TrimSuffix(strings.Repeat("?,", len(nids)), ",")
	for i, n := range nids {
		args[i] = n
	}
	rows, err := s.DB.QueryContext(ctx,
		"SELECT nid FROM seed.books WHERE nid IN ("+placeholders+")", args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var nid int64
		if err := rows.Scan(&nid); err != nil {
			return nil, err
		}
		out[nid] = true
	}
	return out, rows.Err()
}

// DiscoveredHit is one official-search hit to write back to user.db
// discovered (converted from crawl.SearchHit at the api layer — the
// store does not import the crawl package).
type DiscoveredHit struct {
	NID      int64
	Title    string
	Author   string
	CoverURL string
	Summary  string
}

// UpsertDiscoveredSearch writes official-search hits that are outside
// the bundled seed (docs/08 §search-remote: the discovery-loop entry).
// Re-hits refresh observed_at; only the fields the search page carries
// are stored (genre/words/favs stay NULL until a detail fetch).
func (s *Store) UpsertDiscoveredSearch(ctx context.Context, hits []DiscoveredHit, observedAt int64) error {
	for _, h := range hits {
		if _, err := s.DB.ExecContext(ctx, `
INSERT INTO discovered(nid, title, author, cover_url, summary, source, observed_at)
VALUES (?, ?, ?, ?, ?, 'search', ?)
ON CONFLICT(nid) DO UPDATE SET
  title = excluded.title,
  author = excluded.author,
  cover_url = excluded.cover_url,
  summary = excluded.summary,
  source = 'search',
  observed_at = excluded.observed_at`,
			h.NID, h.Title, h.Author, h.CoverURL, h.Summary, observedAt); err != nil {
			return err
		}
	}
	return nil
}

// DiscoveredItem is one auto-collected out-of-seed book row (user.db
// discovered — the official-search discovery-loop overlay).
type DiscoveredItem struct {
	NID        int64   `json:"nid"`
	Title      string  `json:"title"`
	Author     *string `json:"author"`
	CoverURL   *string `json:"cover_url"`
	Summary    *string `json:"summary"`
	Source     string  `json:"source"`
	ObservedAt int64   `json:"observed_at"`
}

// ListDiscovered returns auto-collected books, most recently collected
// first (docs/08 §discovered).
func (s *Store) ListDiscovered(ctx context.Context, limit, offset int) ([]DiscoveredItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, title, author, cover_url, summary, source, observed_at
FROM discovered
ORDER BY observed_at DESC, nid ASC
LIMIT ? OFFSET ?`, limit, offset)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []DiscoveredItem{}
	for rows.Next() {
		var (
			it     DiscoveredItem
			author sql.NullString
		)
		if err := rows.Scan(&it.NID, &it.Title, &author, &it.CoverURL,
			&it.Summary, &it.Source, &it.ObservedAt); err != nil {
			return nil, err
		}
		it.Author = strPtr(author)
		items = append(items, it)
	}
	return items, rows.Err()
}

// DeleteDiscovered removes one auto-collected book (user tap on the
// discovery list). The bundled seed is untouched by design.
func (s *Store) DeleteDiscovered(ctx context.Context, nid int64) error {
	_, err := s.DB.ExecContext(ctx, `DELETE FROM discovered WHERE nid = ?`, nid)
	return err
}

// RankingNew is the new-work ranking: last two generations (est_year >=
// gen_max-1) ordered by favs (classic cumulative — the universe
// percentile columns no longer ship, E.30; the cross-generation order is
// an approximation, per docs/03). Licensed books are excluded.
func (s *Store) RankingNew(ctx context.Context, limit int) ([]RankItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, title, author, genre, est_year, favs
FROM seed.books
WHERE est_year >= ? AND is_licensed = 0
ORDER BY favs DESC, est_date DESC, seed.books.nid ASC
LIMIT ?`, s.Manifest.GenMax-1, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]RankItem, 0, limit)
	for rows.Next() {
		var (
			item RankItem
			gen  sql.NullString
			favs sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		items = append(items, item)
	}
	return items, rows.Err()
}

type SearchItem struct {
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	Genre    *string `json:"genre"`
	EstYear  int     `json:"est_year"`
	Favs     *int64  `json:"favs"`
	CoverURL *string `json:"cover_url"`
	// InSeed = the row comes from the bundled seed rather than the
	// discovery overlay (auto-collected official-search hits). False
	// rows carry no est_year/favs until a detail fetch.
	InSeed bool `json:"in_seed"`
}

// InsertObservation appends an alive-state observation (docs/05 §5.1: the
// only source of metric truth; (nid, observed_at) dedupes same-second
// fetches). Only seed.db stays untouched; this writes user.db.
func (s *Store) InsertObservation(ctx context.Context, nid, observedAt int64,
	clicks, favs, praises, words *int64, status, updatedAt *string) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT OR IGNORE INTO observations(nid, observed_at, clicks, favs, praises, words,
 status, updated_at, source)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'detail')`,
		nid, observedAt, clicks, favs, praises, words, status, updatedAt)
	return err
}

// Observations returns a nid's observation history, newest first.
func (s *Store) Observations(ctx context.Context, nid int64) ([]Observation, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT observed_at, clicks, favs, praises, words, short_comments,
       long_comments, status, updated_at, source
FROM observations WHERE nid = ? ORDER BY observed_at DESC`, nid)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	// Non-nil empty slice: JSON must be [] not null (Dart side expects a list).
	items := []Observation{}
	for rows.Next() {
		var (
			o                     Observation
			clicks, favs, praises sql.NullInt64
			words, shortC, longC  sql.NullInt64
			status, updatedAt     sql.NullString
		)
		if err := rows.Scan(&o.ObservedAt, &clicks, &favs, &praises, &words,
			&shortC, &longC, &status, &updatedAt, &o.Source); err != nil {
			return nil, err
		}
		o.Clicks = intPtr(clicks)
		o.Favs = intPtr(favs)
		o.Praises = intPtr(praises)
		o.Words = intPtr(words)
		o.ShortComments = intPtr(shortC)
		o.LongComments = intPtr(longC)
		o.Status = strPtr(status)
		o.UpdatedAt = strPtr(updatedAt)
		items = append(items, o)
	}
	return items, rows.Err()
}

// CalendarBook is one seed book on the release calendar (docs/14 P1):
// est_date dating + conf tier. Display-only; the recommendation layer
// never consumes calendar data.
type CalendarBook struct {
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	Genre    *string `json:"genre"`
	Favs     int64   `json:"favs"`
	CoverURL *string `json:"cover_url"`
	EstDate  string  `json:"est_date"`
	EstConf  string  `json:"est_conf"`
}

// CalendarDay is one date cell of the release calendar. Items carries
// the favourites-top books and is set only for day/week granularity;
// the month view keeps totals only (its cells are too small for cards).
type CalendarDay struct {
	Date  string `json:"date"`
	Total int    `json:"total"`
	// Universe is the estimated whole-platform release count for this
	// date (calendar_universe, seed schema v4, app/docs/14) — the bundled
	// seed (Total) is a clickable subset of it. 0 = no row in the table.
	Universe int            `json:"universe"`
	Items    []CalendarBook `json:"items,omitempty"`
}

// BooksByDateRange returns seed books whose est_date falls in
// [from, to] (YYYY-MM-DD inclusive), grouped by date, favourites desc
// inside each cell (docs/14 §1.2). The calendar is a display-only view
// over the stats universe: licensed books are excluded, matching the
// generation boards. With excludeLow the est_conf='low' rows (anchor gap
// > 365d) are dropped — they are only reliable in the month view
// (docs/14 §1.3). est_date carries no index on purpose: the full seed
// scan is <10 ms on 30k rows.
func (s *Store) BooksByDateRange(ctx context.Context, from, to string, excludeLow bool, perCell int) ([]CalendarDay, error) {
	q := `SELECT nid, title, author, genre, favs, cover_url, est_date, est_conf
FROM books
WHERE est_date >= ? AND est_date <= ? AND is_licensed = 0`
	args := []any{from, to}
	if excludeLow {
		q += ` AND est_conf != 'low'`
	}
	q += `
ORDER BY est_date ASC, favs DESC, nid ASC`
	rows, err := s.DB.QueryContext(ctx, q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var days []CalendarDay
	cur := ""
	for rows.Next() {
		var b CalendarBook
		if err := rows.Scan(&b.NID, &b.Title, &b.Author, &b.Genre, &b.Favs, &b.CoverURL, &b.EstDate, &b.EstConf); err != nil {
			return nil, err
		}
		if b.EstDate != cur {
			days = append(days, CalendarDay{Date: b.EstDate})
			cur = b.EstDate
		}
		cell := &days[len(days)-1]
		cell.Total++
		if len(cell.Items) < perCell {
			cell.Items = append(cell.Items, b)
		}
	}
	return days, rows.Err()
}

// UniverseCountByDay returns the estimated whole-platform releases per
// date (calendar_universe, seed schema v4) over [from, to]. Days without
// a book are absent from the map; callers fill zeros.
func (s *Store) UniverseCountByDay(ctx context.Context, from, to string) (map[string]int, error) {
	rows, err := s.DB.QueryContext(ctx,
		`SELECT day, universe_count FROM calendar_universe WHERE day >= ? AND day <= ?`,
		from, to)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make(map[string]int)
	for rows.Next() {
		var day string
		var n int
		if err := rows.Scan(&day, &n); err != nil {
			return nil, err
		}
		out[day] = n
	}
	return out, rows.Err()
}

// RetentionDays is the observation retention window (docs 02 §3.1:
// keep 180 days, delete in bulk, no VACUUM).
const RetentionDays = 180

// PruneObservations deletes observations older than the retention window
// and returns the number of rows removed. It runs at engine start and only
// ever touches user.db.
func (s *Store) PruneObservations(ctx context.Context, now time.Time) (int64, error) {
	cutoff := now.AddDate(0, 0, -RetentionDays).Unix()
	res, err := s.DB.ExecContext(ctx,
		`DELETE FROM observations WHERE observed_at < ?`, cutoff)
	if err != nil {
		return 0, err
	}
	n, _ := res.RowsAffected()
	return n, nil
}

// FeaturedBook is a carousel entry: featured=1 works chosen at seed build
// time (编辑精选).
type FeaturedBook struct {
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	CoverURL *string `json:"cover_url"`
	Favs     *int64  `json:"favs"`
}

// FeaturedBooks returns up to limit featured books for the home carousel.
// An empty form means all forms; otherwise the curated pool is narrowed to
// that form (licensed works stay included).
func (s *Store) FeaturedBooks(ctx context.Context, limit int,
	form string) ([]FeaturedBook, error) {
	return s.featured(ctx, limit, 0,
		"ORDER BY favs DESC, seed.books.nid ASC", form)
}

// FeaturedAll returns one page of the featured=1 pool (编辑精选, includes
// licensed works) for the 大图精选 "更多" gallery. order "asc" inverts the
// default favs DESC; nid is the tie-breaker so pages are stable. (nid must
// be qualified: the covers table also has a nid column.)
func (s *Store) FeaturedAll(ctx context.Context, limit, offset int,
	order string) ([]FeaturedBook, error) {
	dir := "DESC"
	if order == "asc" {
		dir = "ASC"
	}
	return s.featured(ctx, limit, offset,
		"ORDER BY favs "+dir+", seed.books.nid ASC", "")
}

// featured is the shared query for the featured=1 pool (编辑精选,
// includes licensed works): static favs order or random reroll.
func (s *Store) featured(ctx context.Context, limit, offset int,
	orderBy, form string) ([]FeaturedBook, error) {
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url, seed.books.favs
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE featured = 1`
	args := []any{}
	if form != "" {
		query += " AND seed.books.form = ?"
		args = append(args, form)
	}
	query += "\n" + orderBy + `
LIMIT ? OFFSET ?`
	args = append(args, limit, offset)
	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []FeaturedBook{}
	for rows.Next() {
		var (
			it    FeaturedBook
			cover sql.NullString
			favs  sql.NullInt64
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &cover, &favs); err != nil {
			return nil, err
		}
		it.CoverURL = strPtr(cover)
		it.Favs = intPtr(favs)
		items = append(items, it)
	}
	return items, rows.Err()
}

// UpsertBookMeta persists every field returned by one detail fetch. Nil
// fields (not returned by that pathway) never overwrite an older value, so
// the mobile HTML baseline and the App API enhancement can coexist.
func (s *Store) UpsertBookMeta(ctx context.Context, m *BookMeta) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO book_meta(nid, source, fetched_at, title, author, author_id,
 genre, type_id, price_type, status, cover_url, summary, words, favs, praises,
 clicks, updated_at, add_time, point, bg_banner, category_id, is_sensitive,
 allow_down)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(nid) DO UPDATE SET
 source=excluded.source, fetched_at=excluded.fetched_at,
 title=COALESCE(excluded.title, book_meta.title),
 author=COALESCE(excluded.author, book_meta.author),
 author_id=COALESCE(excluded.author_id, book_meta.author_id),
 genre=COALESCE(excluded.genre, book_meta.genre),
 type_id=COALESCE(excluded.type_id, book_meta.type_id),
 price_type=COALESCE(excluded.price_type, book_meta.price_type),
 status=COALESCE(excluded.status, book_meta.status),
 cover_url=COALESCE(excluded.cover_url, book_meta.cover_url),
 summary=COALESCE(excluded.summary, book_meta.summary),
 words=COALESCE(excluded.words, book_meta.words),
 favs=COALESCE(excluded.favs, book_meta.favs),
 praises=COALESCE(excluded.praises, book_meta.praises),
 clicks=COALESCE(excluded.clicks, book_meta.clicks),
 updated_at=COALESCE(excluded.updated_at, book_meta.updated_at),
 add_time=COALESCE(excluded.add_time, book_meta.add_time),
 point=COALESCE(excluded.point, book_meta.point),
 bg_banner=COALESCE(excluded.bg_banner, book_meta.bg_banner),
 category_id=COALESCE(excluded.category_id, book_meta.category_id),
 is_sensitive=COALESCE(excluded.is_sensitive, book_meta.is_sensitive),
 allow_down=COALESCE(excluded.allow_down, book_meta.allow_down)`,
		m.NID, m.Source, m.FetchedAt, m.Title, m.Author, m.AuthorID,
		m.Genre, m.TypeID, m.PriceType, m.Status, m.CoverURL, m.Summary,
		m.Words, m.Favs, m.Praises, m.Clicks, m.UpdatedAt, m.AddTime,
		m.Point, m.BgBanner, m.CategoryID, m.IsSensitive, m.AllowDown)
	return err
}

// BookMeta reads the local metadata overlay for a nid, if any.
func (s *Store) BookMeta(ctx context.Context, nid int64) (*BookMeta, error) {
	const q = `
SELECT nid, source, fetched_at, title, author, author_id, genre, type_id,
 price_type, status, cover_url, summary, words, favs, praises, clicks,
 updated_at, add_time, point, bg_banner, category_id, is_sensitive, allow_down
FROM book_meta WHERE nid = ?`
	var (
		m                                              BookMeta
		title, author, genre, priceType, status, cover sql.NullString
		summary, updatedAt, addTime, bgBanner          sql.NullString
		authorID, typeID, words, favs, praises, clicks sql.NullInt64
		categoryID, isSensitive, allowDown             sql.NullInt64
		point                                          sql.NullFloat64
	)
	err := s.DB.QueryRowContext(ctx, q, nid).Scan(
		&m.NID, &m.Source, &m.FetchedAt, &title, &author, &authorID, &genre,
		&typeID, &priceType, &status, &cover, &summary, &words, &favs,
		&praises, &clicks, &updatedAt, &addTime, &point, &bgBanner,
		&categoryID, &isSensitive, &allowDown,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	m.Title = strPtr(title)
	m.Author = strPtr(author)
	m.AuthorID = intPtr(authorID)
	m.Genre = strPtr(genre)
	m.TypeID = intPtr(typeID)
	m.PriceType = strPtr(priceType)
	m.Status = strPtr(status)
	m.CoverURL = strPtr(cover)
	m.Summary = strPtr(summary)
	m.Words = intPtr(words)
	m.Favs = intPtr(favs)
	m.Praises = intPtr(praises)
	m.Clicks = intPtr(clicks)
	m.UpdatedAt = strPtr(updatedAt)
	m.AddTime = strPtr(addTime)
	m.Point = floatPtr(point)
	m.BgBanner = strPtr(bgBanner)
	m.CategoryID = intPtr(categoryID)
	m.IsSensitive = boolPtr(isSensitive)
	m.AllowDown = boolPtr(allowDown)
	return &m, nil
}

// RefreshAttempt reads the last user-triggered detail fetch for a nid.
// A nil result means the book has never been refreshed on this device.
func (s *Store) RefreshAttempt(ctx context.Context, nid int64) (*RefreshAttempt, error) {
	var a RefreshAttempt
	err := s.DB.QueryRowContext(ctx, `
SELECT nid, attempted_at, state FROM refresh_attempts WHERE nid = ?`, nid).
		Scan(&a.NID, &a.AttemptedAt, &a.State)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &a, nil
}

// RecordRefreshAttempt stamps an outbound detail request. It is written
// before the request so a failure still consumes the cooldown window.
func (s *Store) RecordRefreshAttempt(ctx context.Context, nid, attemptedAt int64, state string) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO refresh_attempts(nid, attempted_at, state) VALUES (?, ?, ?)
ON CONFLICT(nid) DO UPDATE SET
  attempted_at=excluded.attempted_at, state=excluded.state`,
		nid, attemptedAt, state)
	return err
}

// FinishRefreshAttempt updates the state of the attempt that is still current.
// If a newer attempt has already been stamped, the update is a no-op.
func (s *Store) FinishRefreshAttempt(ctx context.Context, nid, attemptedAt int64, state string) error {
	_, err := s.DB.ExecContext(ctx, `
UPDATE refresh_attempts SET state = ? WHERE nid = ? AND attempted_at = ?`,
		state, nid, attemptedAt)
	return err
}

// Pref reads a user preference. ok=false means the key is absent.
func (s *Store) Pref(ctx context.Context, key string) (value string, ok bool, err error) {
	err = s.DB.QueryRowContext(ctx, `SELECT value FROM prefs WHERE key = ?`, key).
		Scan(&value)
	if errors.Is(err, sql.ErrNoRows) {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	return value, true, nil
}

// SetPref writes a user preference.
func (s *Store) SetPref(ctx context.Context, key, value string) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO prefs(key, value) VALUES (?, ?)
ON CONFLICT(key) DO UPDATE SET value=excluded.value`, key, value)
	return err
}

// OfficialRanksGet returns the cached official-ranks response body when it
// is still within [ttl]; ok=false on a miss or expiry. The table survives
// process restarts (the in-memory cache does not) — v9.
func (s *Store) OfficialRanksGet(ctx context.Context, key string, ttl time.Duration) ([]byte, bool, error) {
	var (
		body      string
		fetchedAt int64
	)
	err := s.DB.QueryRowContext(ctx,
		`SELECT body, fetched_at FROM official_ranks_cache WHERE key = ?`, key).
		Scan(&body, &fetchedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	if time.Now().Unix()-fetchedAt > int64(ttl.Seconds()) {
		return nil, false, nil
	}
	return []byte(body), true, nil
}

// OfficialRanksPut stores one fetched official-ranks response body (v9).
func (s *Store) OfficialRanksPut(ctx context.Context, key string, body []byte) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO official_ranks_cache(key, fetched_at, body) VALUES (?, ?, ?)
ON CONFLICT(key) DO UPDATE SET fetched_at=excluded.fetched_at,
    body=excluded.body`, key, time.Now().Unix(), body)
	return err
}

// UpsertCover stores an App API novelCover under the nid. Covers are
// book attributes (not observations) and live only in user.db.
func (s *Store) UpsertCover(ctx context.Context, nid int64, cover string, fetchedAt int64) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO covers(nid, cover, source, fetched_at) VALUES (?, ?, 'app', ?)
ON CONFLICT(nid) DO UPDATE SET cover=excluded.cover,
 source=excluded.source, fetched_at=excluded.fetched_at`,
		nid, cover, fetchedAt)
	return err
}

// RecordBrowsing bumps the browsing footprint for a nid (upsert: the latest
// open wins). Pure local data in user.db.
func (s *Store) RecordBrowsing(ctx context.Context, nid, viewedAt int64) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO browsing_history(nid, viewed_at) VALUES (?, ?)
ON CONFLICT(nid) DO UPDATE SET viewed_at=excluded.viewed_at`,
		nid, viewedAt)
	return err
}

// HistoryItem is one browsing footprint row joined with seed metadata.
type HistoryItem struct {
	NID      int64   `json:"nid"`
	Title    string  `json:"title"`
	Author   string  `json:"author"`
	Genre    *string `json:"genre"`
	ViewedAt int64   `json:"viewed_at"`
}

// RecentHistory returns the most recently opened books, newest first.
func (s *Store) RecentHistory(ctx context.Context, limit int) ([]HistoryItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT h.nid, COALESCE(b.title, ''), COALESCE(b.author, ''), b.genre, h.viewed_at
FROM browsing_history h
LEFT JOIN seed.books b ON b.nid = h.nid
ORDER BY h.viewed_at DESC LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []HistoryItem{}
	for rows.Next() {
		var (
			it    HistoryItem
			genre sql.NullString
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &genre, &it.ViewedAt); err != nil {
			return nil, err
		}
		it.Genre = strPtr(genre)
		items = append(items, it)
	}
	return items, rows.Err()
}

// BannerPick deterministically shuffles the banner pool (seed featured=1,
// licensed works included — banners are display-layer) with the date as the
// random seed. Same seed → same set, every day a different draw, and every
// banner stays reachable because the shuffle is a uniform reorder.
// The seed must enter the hash with a coefficient whose residue mod M
// is a large fraction of the 1,000,003-bucket key space: the cut point
// then moves ~half the circle per day, so consecutive days draw the
// opposite arc — genuinely different top-k. The old additive seed
// (nid*a + day, B=1) advanced one bucket per day, so top-k never
// changed (user-reported 2026-11-20: today == yesterday); B=996940
// (≡ -3063) was no better for small pools. B = 500001 (half circle).
// Pure arithmetic: this SQLite build predates the ^ operator.
// BannerPick returns a seeded deterministic segment of the featured=1
// pool: the whole pool is shuffled by (nid, seed), then rows [offset,
// offset+limit) are taken. Sharing one seed across calls with different
// offsets segments the pool without overlap — the daily banner carousel
// and the 大图精选 section use the same day seed, offset 0 and N.
// An empty form means all forms; otherwise only that form is shuffled.
func (s *Store) BannerPick(ctx context.Context, seed int64, offset int,
	limit int, form string) ([]FeaturedBook, error) {
	query := `
SELECT seed.books.nid, seed.books.title, seed.books.author,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url, seed.books.favs
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE featured = 1`
	args := []any{}
	if form != "" {
		query += " AND seed.books.form = ?"
		args = append(args, form)
	}
	query += `
ORDER BY (seed.books.nid*2654435761 + ?*500001) % 1000003, seed.books.nid
LIMIT ? OFFSET ?`
	args = append(args, seed, limit, offset)
	rows, err := s.DB.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []FeaturedBook{}
	for rows.Next() {
		var (
			it    FeaturedBook
			cover sql.NullString
			favs  sql.NullInt64
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &cover, &favs); err != nil {
			return nil, err
		}
		it.CoverURL = strPtr(cover)
		it.Favs = intPtr(favs)
		items = append(items, it)
	}
	return items, rows.Err()
}

// CoverURLs returns the best-known cover for each nid: a locally fetched
// cover wins over the seed cover_url. Missing nids are omitted. Official PC
// rank rows carry no <img>, so the API joins them back to the seed here.
func (s *Store) CoverURLs(ctx context.Context, nids []int64) (map[int64]string, error) {
	out := make(map[int64]string, len(nids))
	if len(nids) == 0 {
		return out, nil
	}
	placeholders := strings.TrimSuffix(strings.Repeat("?,", len(nids)), ",")
	args := make([]any, len(nids))
	for i, nid := range nids {
		args[i] = nid
	}
	rows, err := s.DB.QueryContext(ctx, `
SELECT seed.books.nid, COALESCE(c.cover, NULLIF(seed.books.cover_url, ''))
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE seed.books.nid IN (`+placeholders+`)`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var nid int64
		var cover sql.NullString
		if err := rows.Scan(&nid, &cover); err != nil {
			return nil, err
		}
		if cover.Valid && cover.String != "" {
			out[nid] = cover.String
		}
	}
	return out, rows.Err()
}

// SeedFromRank writes a minimal book_meta row from an official-rank entry
// (docs/08 §rank-seed) so the detail page renders instantly instead of
// 404-ing into a blocking collect. Existing rows are never downgraded:
// basic fields are filled only when empty; full fetch data (words, favs,
// summary, …) is left to the standard refresh path.
func (s *Store) SeedFromRank(ctx context.Context, nid int64, title, author, coverURL, genre string) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT INTO book_meta(nid, source, fetched_at, title, author, cover_url, genre)
VALUES (?, 'rank', ?, ?, ?, ?, ?)
ON CONFLICT(nid) DO UPDATE SET
  title     = COALESCE(NULLIF(book_meta.title, ''), excluded.title),
  author    = COALESCE(NULLIF(book_meta.author, ''), excluded.author),
  cover_url = COALESCE(NULLIF(book_meta.cover_url, ''), excluded.cover_url),
  genre     = COALESCE(NULLIF(book_meta.genre, ''), excluded.genre)`,
		nid, time.Now().Unix(), title, author, coverURL, genre)
	return err
}

// Cover returns the locally fetched cover path for a nid, if any.
func (s *Store) Cover(ctx context.Context, nid int64) (string, error) {
	var cover string
	err := s.DB.QueryRowContext(ctx,
		`SELECT cover FROM covers WHERE nid = ?`, nid).Scan(&cover)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return cover, nil
}

func strPtr(v sql.NullString) *string {
	if !v.Valid {
		return nil
	}
	s := v.String
	return &s
}

// NormalizeContest collapses multi-division contest names to the
// event-level name (user 2026-11-21): only the N征 series is multi-division
// (六征 splits into 长篇/中篇/短篇; 七征 also carries a 对话类 division), so
// the trailing 篇幅 suffix is stripped only from N征* names — every other
// contest name is returned unchanged (it is a single-event contest).
func NormalizeContest(s string) string {
	if !isZhengEvent(s) {
		return s
	}
	for _, suf := range []string{"长篇", "中篇", "短篇"} {
		if strings.HasSuffix(s, suf) {
			return strings.TrimSuffix(s, suf)
		}
	}
	return s
}

// isZhengEvent reports whether s starts with a Chinese-numeral 征 event
// prefix: one or more of 一二三四五六七八九十, then 征 (五征, 十三征,
// 七征对话类征文 …). A 征 without a numeral prefix does not match.
func isZhengEvent(s string) bool {
	digits := false
	for _, r := range s {
		if strings.ContainsRune("一二三四五六七八九十", r) {
			digits = true
			continue
		}
		return digits && r == '征'
	}
	return false
}

// contestPtr is strPtr + NormalizeContest: every contest value the API
// returns is event-level (六征长篇 → 六征).
func contestPtr(v sql.NullString) *string {
	p := strPtr(v)
	if p == nil {
		return nil
	}
	s := NormalizeContest(*p)
	return &s
}

// contestMatchClause returns a WHERE fragment matching one event-level
// contest name against the raw column (see contestEventMatch in
// contests.go). col is the column reference, optionally table-qualified.
func contestMatchClause(col, name string) (string, []any) {
	return contestEventMatch(col, name)
}

// mergeContestGroups folds 征-series divisions into their event name (see
// NormalizeContest) and re-sorts by merged count DESC, name ASC.
func mergeContestGroups(groups []IpGroup) []IpGroup {
	merged := map[string]int{}
	for _, g := range groups {
		merged[NormalizeContest(g.Contest)] += g.Count
	}
	out := make([]IpGroup, 0, len(merged))
	for name, count := range merged {
		out = append(out, IpGroup{Contest: name, Count: count})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Count != out[j].Count {
			return out[i].Count > out[j].Count
		}
		return out[i].Contest < out[j].Contest
	})
	return out
}

func intPtr(v sql.NullInt64) *int64 {
	if !v.Valid {
		return nil
	}
	n := v.Int64
	return &n
}

func floatPtr(v sql.NullFloat64) *float64 {
	if !v.Valid {
		return nil
	}
	f := v.Float64
	return &f
}

func boolPtr(v sql.NullInt64) *bool {
	if !v.Valid {
		return nil
	}
	b := v.Int64 != 0
	return &b
}

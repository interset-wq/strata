package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
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
	FavPctl    *float64 `json:"fav_pctl"`
	ClickPctl  *float64 `json:"click_pctl"`
	PraisePctl *float64 `json:"praise_pctl"`
	PR         *float64 `json:"pr"`
	PctlPR     *float64 `json:"pctl_pr"`
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
       est_conf, tags, fav_pctl, click_pctl, praise_pctl, pr, pctl_pr, form,
       is_licensed
FROM seed.books WHERE nid = ?`

	var (
		b                                          Book
		genre, priceType, status, contest, cover   sql.NullString
		words, clicks, favs, praises, featured     sql.NullInt64
		updatedAt, tags                            sql.NullString
		favPctl, clickPctl, praisePctl, pr, pctlPR sql.NullFloat64
		form                                       string
		isLicensed                                 sql.NullInt64
	)
	err := s.DB.QueryRowContext(ctx, q, nid).Scan(
		&b.NID, &b.Title, &b.Author, &genre, &priceType, &status, &contest,
		&words, &clicks, &favs, &praises, &featured, &cover, &updatedAt,
		&b.EstYear, &b.EstDate, &b.EstConf, &tags,
		&favPctl, &clickPctl, &praisePctl, &pr, &pctlPR, &form, &isLicensed,
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
	b.Contest = strPtr(contest)
	b.Words = intPtr(words)
	b.Clicks = intPtr(clicks)
	b.Favs = intPtr(favs)
	b.Praises = intPtr(praises)
	b.Featured = featured.Valid && featured.Int64 != 0
	b.CoverURL = strPtr(cover)
	b.UpdatedAt = strPtr(updatedAt)
	b.Tags = strPtr(tags)
	b.FavPctl = floatPtr(favPctl)
	b.ClickPctl = floatPtr(clickPctl)
	b.PraisePctl = floatPtr(praisePctl)
	b.PR = floatPtr(pr)
	b.PctlPR = floatPtr(pctlPR)
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
	return &BookDetail{Book: &b, Tags: tagList, Local: local, Meta: meta}, nil
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
	Favs     *int64   `json:"favs"`
	FavPctl  float64  `json:"fav_pctl"`
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
       seed.books.est_year, seed.books.favs, seed.books.fav_pctl, seed.books.contest,
       seed.books.form,
       COALESCE(c.cover, NULLIF(seed.books.cover_url, '')) AS cover_url
FROM seed.books
LEFT JOIN covers c ON c.nid = seed.books.nid
WHERE est_year = ? AND is_licensed = 0 AND fav_pctl IS NOT NULL`
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
		// contest=1 means "any contest entry"; any other value matches one
		// specific contest name exactly.
		if contest == "1" {
			query += " AND contest != ''"
		} else {
			query += " AND contest = ?"
			args = append(args, contest)
		}
	}
	query += " ORDER BY fav_pctl DESC, seed.books.nid ASC LIMIT ?"
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
			pctl    float64
			contest sql.NullString
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs, &pctl, &contest, &item.Form, &item.CoverURL); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		item.FavPctl = pctl
		item.Contest = strPtr(contest)
		items = append(items, item)
	}
	return items, rows.Err()
}

// ClassicBooks is the data-only browse list used by the Classic category,
// status and contest pages. It intentionally sorts by absolute favs, not by
// same-generation percentiles: Classic mode mirrors novly's cumulative view
// and has no quantitative layer.
func (s *Store) ClassicBooks(ctx context.Context, genre, status, contest, form string,
	limit, offset int) ([]RankItem, error) {
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
			query += " AND seed.books.contest = ?"
			args = append(args, contest)
		}
	}
	if form != "" {
		query += " AND seed.books.form = ?"
		args = append(args, form)
	}
	query += " ORDER BY seed.books.favs DESC, seed.books.nid ASC LIMIT ? OFFSET ?"
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
		item.Contest = strPtr(contest)
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
func (s *Store) BoardBooks(ctx context.Context, kind, form string, limit, offset int) ([]RankItem, error) {
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

// WatchAdd puts a book on the author's watchlist (Phase 5 tracking).
func (s *Store) WatchAdd(ctx context.Context, nid int64, addedAt int64) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT OR IGNORE INTO watchlist(nid, role, added_at) VALUES (?, 'self', ?)`,
		nid, addedAt)
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
}

// WatchList joins the watchlist with seed metadata, newest first.
func (s *Store) WatchList(ctx context.Context) ([]WatchItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT w.nid, b.title, b.author, b.genre,
       COALESCE(c.cover, NULLIF(b.cover_url, '')) AS cover_url,
       w.added_at, w.role, w.note
FROM watchlist w JOIN seed.books b ON b.nid = w.nid
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
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &gen,
			&cover, &it.AddedAt, &it.Role, &note); err != nil {
			return nil, err
		}
		it.Genre = strPtr(gen)
		it.CoverURL = strPtr(cover)
		it.Note = strPtr(note)
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
func (s *Store) Search(ctx context.Context, q string, limit int) ([]SearchItem, error) {
	const esc = `\\`
	pattern := "%" + strings.NewReplacer("%", esc+"%", "_", esc+"_", "\\", esc+esc).Replace(q) + "%"
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, title, author, genre, est_year, favs
FROM seed.books
WHERE (title LIKE ? ESCAPE '\' OR author LIKE ? ESCAPE '\')
ORDER BY favs DESC, seed.books.nid ASC
LIMIT ?`, pattern, pattern, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := make([]SearchItem, 0, limit)
	for rows.Next() {
		var (
			item SearchItem
			gen  sql.NullString
			favs sql.NullInt64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs); err != nil {
			return nil, err
		}
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		items = append(items, item)
	}
	return items, rows.Err()
}

// RankingNew is the new-work ranking: last two generations (est_year >=
// gen_max-1) ordered by same-generation percentile, per docs/03. Licensed
// books are excluded.
func (s *Store) RankingNew(ctx context.Context, limit int) ([]RankItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT nid, title, author, genre, est_year, favs, fav_pctl
FROM seed.books
WHERE est_year >= ? AND is_licensed = 0 AND fav_pctl IS NOT NULL
ORDER BY fav_pctl DESC, est_date DESC, seed.books.nid ASC
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
			pctl float64
		)
		if err := rows.Scan(&item.NID, &item.Title, &item.Author, &gen,
			&item.EstYear, &favs, &pctl); err != nil {
			return nil, err
		}
		item.Rank = len(items) + 1
		item.Genre = strPtr(gen)
		item.Favs = intPtr(favs)
		item.FavPctl = pctl
		items = append(items, item)
	}
	return items, rows.Err()
}

type SearchItem struct {
	NID     int64   `json:"nid"`
	Title   string  `json:"title"`
	Author  string  `json:"author"`
	Genre   *string `json:"genre"`
	EstYear int     `json:"est_year"`
	Favs    *int64  `json:"favs"`
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
       long_comments, status, updated_at
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
			&shortC, &longC, &status, &updatedAt); err != nil {
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

type ShelfItem struct {
	NID    int64   `json:"nid"`
	Title  string  `json:"title"`
	Author string  `json:"author"`
	Genre  *string `json:"genre"`
	AddAt  int64   `json:"added_at"`
}

// ShelfAdd records a book into the local shelf (user.db only).
func (s *Store) ShelfAdd(ctx context.Context, nid int64, addedAt int64) error {
	_, err := s.DB.ExecContext(ctx, `
INSERT OR IGNORE INTO shelf(nid, added_at) VALUES (?, ?)`, nid, addedAt)
	return err
}

// ShelfRemove drops a book from the shelf.
func (s *Store) ShelfRemove(ctx context.Context, nid int64) error {
	_, err := s.DB.ExecContext(ctx, `DELETE FROM shelf WHERE nid = ?`, nid)
	return err
}

// ShelfList joins the shelf with seed titles.
func (s *Store) ShelfList(ctx context.Context) ([]ShelfItem, error) {
	rows, err := s.DB.QueryContext(ctx, `
SELECT s.nid, b.title, b.author, b.genre, s.added_at
FROM shelf s JOIN seed.books b ON b.nid = s.nid
ORDER BY s.added_at DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []ShelfItem{}
	for rows.Next() {
		var (
			it    ShelfItem
			genre sql.NullString
		)
		if err := rows.Scan(&it.NID, &it.Title, &it.Author, &genre, &it.AddAt); err != nil {
			return nil, err
		}
		it.Genre = strPtr(genre)
		items = append(items, it)
	}
	return items, rows.Err()
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
ORDER BY (seed.books.nid*2654435761 + ?) % 1000003, seed.books.nid
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

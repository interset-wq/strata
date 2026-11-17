package store

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

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

type BookDetail struct {
	Book  *Book        `json:"book"`
	Tags  []string     `json:"tags"`
	Local *Observation `json:"local"`
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
       est_conf, tags, fav_pctl, click_pctl, praise_pctl, pr, pctl_pr, is_licensed
FROM seed.books WHERE nid = ?`

	var (
		b                                          Book
		genre, priceType, status, contest, cover   sql.NullString
		words, clicks, favs, praises, featured     sql.NullInt64
		updatedAt, tags                            sql.NullString
		favPctl, clickPctl, praisePctl, pr, pctlPR sql.NullFloat64
		isLicensed                                 sql.NullInt64
	)
	err := s.DB.QueryRowContext(ctx, q, nid).Scan(
		&b.NID, &b.Title, &b.Author, &genre, &priceType, &status, &contest,
		&words, &clicks, &favs, &praises, &featured, &cover, &updatedAt,
		&b.EstYear, &b.EstDate, &b.EstConf, &tags,
		&favPctl, &clickPctl, &praisePctl, &pr, &pctlPR, &isLicensed,
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
	b.IsLicensed = isLicensed.Valid && isLicensed.Int64 != 0

	tagList, err := s.bookTags(ctx, nid)
	if err != nil {
		return nil, err
	}
	local, err := s.latestObservation(ctx, nid)
	if err != nil {
		return nil, err
	}
	return &BookDetail{Book: &b, Tags: tagList, Local: local}, nil
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
	Rank    int     `json:"rank"`
	NID     int64   `json:"nid"`
	Title   string  `json:"title"`
	Author  string  `json:"author"`
	Genre   *string `json:"genre"`
	EstYear int     `json:"est_year"`
	Favs    *int64  `json:"favs"`
	FavPctl float64 `json:"fav_pctl"`
}

func (s *Store) RankingFavs(ctx context.Context, year int, genre string, limit int) ([]RankItem, error) {
	query := `
SELECT nid, title, author, genre, est_year, favs, fav_pctl
FROM seed.books
WHERE est_year = ? AND is_licensed = 0 AND fav_pctl IS NOT NULL`
	args := []any{year}
	if genre != "" {
		query += " AND genre = ?"
		args = append(args, genre)
	}
	query += " ORDER BY fav_pctl DESC, nid ASC LIMIT ?"
	args = append(args, limit)

	rows, err := s.DB.QueryContext(ctx, query, args...)
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

type ShortItem struct {
	Rank    int     `json:"rank"`
	NID     int64   `json:"nid"`
	Title   string  `json:"title"`
	Author  string  `json:"author"`
	Genre   *string `json:"genre"`
	EstYear int     `json:"est_year"`
	Favs    *int64  `json:"favs"`
	Words   *int64  `json:"words"`
}

func (s *Store) RankingShort(ctx context.Context, limit int) ([]ShortItem, error) {
	const q = `
SELECT nid, title, author, genre, est_year, favs, words
FROM seed.books
WHERE words <= 50000 AND status = '已完结' AND is_licensed = 0
ORDER BY favs DESC, nid ASC
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
			&item.EstYear, &favs, &words); err != nil {
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

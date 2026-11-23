// Local-data export: the v1 replacement for cloud sync (docs/01 §6 — no
// server, no account). One JSON document with every user-local table
// (observations / watchlist / browsing_history) so the client can share
// the file out of the device. Generic row maps, export-only — no models.
package store

import "context"

// ExportUserData dumps the three user-local tables plus the export stamp.
func (s *Store) ExportUserData(ctx context.Context,
	exportedAt int64) (map[string]any, error) {
	out := map[string]any{"exported_at": exportedAt}
	for _, table := range []string{"observations", "watchlist", "browsing_history"} {
		rows, err := s.dumpTable(ctx, table)
		if err != nil {
			return nil, err
		}
		out[table] = rows
	}
	return out, nil
}

// dumpTable reads one user table as generic row maps (NULL → nil,
// []byte → string) without a per-column model.
func (s *Store) dumpTable(ctx context.Context,
	table string) ([]map[string]any, error) {
	rows, err := s.DB.QueryContext(ctx, "SELECT * FROM "+table)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	cols, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	var out []map[string]any
	for rows.Next() {
		vals := make([]any, len(cols))
		ptrs := make([]any, len(cols))
		for i := range vals {
			ptrs[i] = &vals[i]
		}
		if err := rows.Scan(ptrs...); err != nil {
			return nil, err
		}
		row := make(map[string]any, len(cols))
		for i, c := range cols {
			if b, ok := vals[i].([]byte); ok {
				vals[i] = string(b)
			}
			row[c] = vals[i]
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

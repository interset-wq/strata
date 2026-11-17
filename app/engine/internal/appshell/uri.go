package appshell

import (
	"path/filepath"
	"strings"
)

// FileURI builds a SQLite URI. Query is appended verbatim (for example "mode=ro").
func FileURI(path, query string) string {
	p := filepath.ToSlash(path)
	p = strings.NewReplacer("%", "%25", "?", "%3F", "#", "%23").Replace(p)
	uri := "file:" + p
	if query != "" {
		uri += "?" + query
	}
	return uri
}

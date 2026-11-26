/// 展示层数字/日期格式（无 intl 依赖，docs/01 技术栈）。
library;

/// 千分位：4797 → `4,797`；null → `—`（官方未给，不是 0，也不省略单位）。
String fmtCount(int? v) {
  if (v == null) return '—';
  final s = '$v';
  final out = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) out.write(',');
    out.write(s[i]);
  }
  return '$out';
}

/// 官方赛程日期（`YYYY-MM-DD`）压成行副题用的 `YYYY.MM`。
String fmtMonth(String date) => date.substring(0, 7).replaceAll('-', '.');

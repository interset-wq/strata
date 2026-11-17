import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 书籍详情页：种子数据 + 最新观测的 effective 展示，
/// 附三态刷新（docs/05）与观测历史。
class BookDetailPage extends ConsumerStatefulWidget {
  final int nid;
  const BookDetailPage({super.key, required this.nid});

  @override
  ConsumerState<BookDetailPage> createState() => _BookDetailPageState();
}

class _BookDetailPageState extends ConsumerState<BookDetailPage> {
  bool refreshing = false;
  String? refreshMessage;
  Color? refreshColor;
  bool onShelf = false;
  Future<List<ObservationRow>>? observations;

  @override
  Widget build(BuildContext context) {
    final detail = ref.watch(bookProvider(widget.nid));
    return Scaffold(
      appBar: AppBar(title: Text(detail.value?.book['title']?.toString() ?? '详情')),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('加载失败：$e')),
        data: (d) {
          final b = d.book;
          // effective = 种子值被最新本地观测覆盖后的展示值（契约 08）。
          final eff = (d.effective ?? const {}).cast<String, dynamic>();

          String? s(Object? v) => v?.toString();
          final licensed = b['is_licensed'] == true;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(s(b['title']) ?? '',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 6),
              Text('${s(b['author']) ?? ''} · ${s(b['est_year']) ?? ''}'
                  '${s(b['genre']) != null ? ' · ${s(b['genre'])}' : ''}'),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                children: [
                  for (final tag in d.tags) Chip(label: Text(tag)),
                ],
              ),
              const SizedBox(height: 12),
              if (licensed)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: Text(
                    '授权作品（is_licensed=1）：可搜索、可看详情，不参与榜单与统计',
                    style: TextStyle(color: Colors.deepOrange),
                  ),
                ),
              // 六指标格：点击/收藏/推荐/字数（短评/长评来自观测，种子无）
              _metricGrid(context, eff, b),
              _pctlCard(context, b),
              _metaCard(context, d, eff, b),
              const SizedBox(height: 12),
              Row(
                children: [
                  FilledButton.icon(
                    onPressed: refreshing ? null : () => _refresh(context),
                    icon: refreshing
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.refresh),
                    label: const Text('刷新观测'),
                  ),
                  const SizedBox(width: 12),
                  onShelf
                      ? OutlinedButton.icon(
                          onPressed: _removeShelf,
                          icon: const Icon(Icons.favorite),
                          label: const Text('已在书架'),
                        )
                      : OutlinedButton.icon(
                          onPressed: _addShelf,
                          icon: const Icon(Icons.favorite_border),
                          label: const Text('收藏'),
                        ),
                ],
              ),
              if (refreshMessage != null) ...[
                const SizedBox(height: 8),
                Text(refreshMessage!,
                    style: TextStyle(color: refreshColor)),
              ],
              const Divider(height: 32),
              Text('观测历史',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              _observationsList(),
            ],
          );
        },
      ),
    );
  }

  Future<void> _refresh(BuildContext context) async {
    setState(() => refreshing = true);
    try {
      final handle = await ref.read(bootProvider.future);
      final r = await handle.api.refresh(widget.nid);
      setState(() {
        switch (r.state) {
          case 'alive':
            refreshMessage = '观测已写入（favs=${r.detail?['favs']}）';
            refreshColor = Colors.green;
          case 'dead':
            refreshMessage = '官方页面不存在（未写观测）';
            refreshColor = Colors.deepOrange;
          case 'zombie':
            refreshMessage = '该书当前不可阅读（未写观测）';
            refreshColor = Colors.deepOrange;
          default:
            refreshMessage = '未知状态：${r.state}';
            refreshColor = Colors.red;
        }
      });
      ref.invalidate(bookProvider(widget.nid));
      setState(() {
        observations = handle.api.observations(widget.nid);
      });
    } catch (e) {
      setState(() {
        refreshMessage = '刷新失败：$e';
        refreshColor = Colors.red;
      });
    } finally {
      setState(() => refreshing = false);
    }
  }

  Future<void> _addShelf() async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.shelfAdd(widget.nid);
    setState(() => onShelf = true);
  }

  Future<void> _removeShelf() async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.shelfRemove(widget.nid);
    setState(() => onShelf = false);
  }

  Widget _observationsList() {
    observations ??=
        ref.read(bootProvider.future).then((h) => h.api.observations(widget.nid));
    return FutureBuilder<List<ObservationRow>>(
      future: observations,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snap.hasError) {
          return Text('观测加载失败：${snap.error}');
        }
        final items = snap.data ?? [];
        if (items.isEmpty) {
          return const Text('暂无本地观测，点上方「刷新观测」开始累积',
              style: TextStyle(color: Colors.grey));
        }
        return Column(
          children: [
            for (final o in items)
              ListTile(
                dense: true,
                title: Text(
                    '${DateTime.fromMillisecondsSinceEpoch(o.observedAt * 1000)}'
                    .replaceAll('.000', '')),
                subtitle: Text(
                    '收藏 ${o.favs ?? '-'} · 赞 ${o.praises ?? '-'} · 字数 ${o.words ?? '-'}'),
              ),
          ],
        );
      },
    );
  }

  String? _num(Object? v) {
    if (v == null) return null;
    final s = v.toString();
    if (s.isEmpty || s == 'null') return null;
    final n = int.tryParse(s);
    if (n == null) return s;
    // 大数字缩写：≥1亿用亿、≥1万用万，避免溢出换行
    final abs = n.abs();
    if (abs >= 100000000) {
      return '${(n / 100000000).toStringAsFixed(2)}亿';
    }
    if (abs >= 10000) {
      return '${(n / 10000).toStringAsFixed(1)}万';
    }
    return n.toString();
  }

  /// 六指标格（设计稿：尽可能多展示数据；短评/长评由观测通路提供，待接入）。
  Widget _metricGrid(BuildContext context, Map<String, dynamic> eff,
      Map<String, dynamic> b) {
    String v(String key) => _num(eff[key] ?? b[key]) ?? '—';
    final scheme = Theme.of(context).colorScheme;
    final labels = [('点击', 'clicks'), ('收藏', 'favs'), ('推荐', 'praises'), ('字数', 'words')];
    return Row(
      children: [
        for (final (label, key) in labels)
          Expanded(
            child: Card(
              margin: const EdgeInsets.symmetric(horizontal: 4),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 10),
                child: Column(
                  children: [
                    Text(label,
                        style: TextStyle(
                            fontSize: 10, color: scheme.onSurfaceVariant)),
                    const SizedBox(height: 3),
                    Text(v(key),
                        style: Theme.of(context)
                            .textTheme
                            .titleLarge
                            ?.copyWith(fontSize: 15)),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }

  /// 同代分位对照条（种子的 fav/click/praise 分位 + PR 复合指标）。
  Widget _pctlCard(BuildContext context, Map<String, dynamic> b) {
    final scheme = Theme.of(context).colorScheme;
    double? pct(Object? v) {
      final d = double.tryParse(v?.toString() ?? '');
      return d;
    }

    Widget bar(String label, double? p) {
      final shown = p == null ? null : (p.clamp(0, 1) * 100);
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label,
                  style: TextStyle(
                      fontSize: 11, color: scheme.onSurfaceVariant)),
              Text(shown == null ? '—' : '${shown.toStringAsFixed(1)}%',
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: scheme.primary)),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: shown == null ? 0 : shown / 100,
              minHeight: 6,
              backgroundColor: scheme.primary.withValues(alpha: .12),
            ),
          ),
          const SizedBox(height: 10),
        ],
      );
    }

    final pr = pct(b['pr']);
    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('同代分位（est_year 参照系）',
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 10),
            bar('收藏分位', pct(b['fav_pctl'])),
            bar('点击分位', pct(b['click_pctl'])),
            bar('推荐分位', pct(b['praise_pctl'])),
            if (pr != null)
              Text('PR（赞/藏）${pr.toStringAsFixed(3)}',
                  style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: scheme.secondary)),
          ],
        ),
      ),
    );
  }

  /// 完整元数据卡（数据全展示原则）。
  Widget _metaCard(BuildContext context, BookDetail d, Map<String, dynamic> eff,
      Map<String, dynamic> b) {
    String? s(Object? v) => v?.toString();
    Widget row(String label, String? value) {
      if (value == null || value.isEmpty || value == 'null') {
        return const SizedBox.shrink();
      }
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: TextStyle(
                    fontSize: 12,
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
            Flexible(
              child: Text(value,
                  textAlign: TextAlign.right,
                  style: const TextStyle(fontSize: 12)),
            ),
          ],
        ),
      );
    }

    return Card(
      margin: const EdgeInsets.only(top: 12),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('元数据',
                style: TextStyle(
                    fontSize: 12,
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
            const SizedBox(height: 6),
            row('状态', eff['status']?.toString() ?? s(b['status'])),
            row('上架日期', s(b['est_date'])),
            row('收录置信度', s(b['est_conf'])),
            row('价格类型', s(b['price_type'])),
            row('比赛', s(b['contest'])),
            row('featured', b['featured'] == true ? '是（编辑精选）' : null),
            row('官方更新时间', s(b['updated_at'])),
            row('数据来源', d.source == 'local' ? '本地观测' : '种子'),
            row('数据截止', d.dataEnd),
          ],
        ),
      ),
    );
  }
}

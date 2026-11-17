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
          String? effStr(String key, {Object? seed}) {
            final v = eff[key] ?? seed;
            return v?.toString();
          }

          String? s(Object? v) => v?.toString();
          final licensed = b['is_licensed'] == true;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(s(b['title']) ?? '',
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
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
              _row('收藏', effStr('favs', seed: b['favs'])),
              _row('点击', effStr('clicks', seed: b['clicks'])),
              _row('推荐', effStr('praises', seed: b['praises'])),
              _row('字数', effStr('words', seed: b['words'])),
              _row('状态', effStr('status', seed: b['status'])),
              _row('更新时间', effStr('updated_at', seed: b['updated_at'])),
              _row('数据来源', d.source == 'local' ? '本地观测' : '种子'),
              _row('数据截止', d.dataEnd),
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

  Widget _row(String label, String? value) {
    if (value == null || value.isEmpty || value == 'null') {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

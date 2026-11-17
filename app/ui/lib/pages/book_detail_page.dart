import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/providers.dart';

/// 书籍详情页：种子数据 + 最新观测的 effective 展示。
class BookDetailPage extends ConsumerWidget {
  final int nid;
  const BookDetailPage({super.key, required this.nid});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(bookProvider(nid));
    return Scaffold(
      appBar: AppBar(title: Text(detail.value?.book['title']?.toString() ?? '详情')),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('加载失败：$e')),
        data: (d) {
          final b = d.book;
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
              _row('收藏', s(b['favs'])),
              _row('点击', s(b['clicks'])),
              _row('推荐', s(b['praises'])),
              _row('字数', s(b['words'])),
              _row('状态', s(b['status'])),
              _row('更新时间', s(b['updated_at'])),
              _row('数据来源', d.source == 'local' ? '本地观测' : '种子'),
              _row('数据截止', d.dataEnd),
            ],
          );
        },
      ),
    );
  }

  Widget _row(String label, String? value) {
    if (value == null || value.isEmpty || value == 'null') return const SizedBox.shrink();
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

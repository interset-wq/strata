import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';

/// 书架页：列出本地收藏（user.db.shelf JOIN seed.books），点条目进详情。
class ShelfPage extends ConsumerStatefulWidget {
  const ShelfPage({super.key});

  @override
  ConsumerState<ShelfPage> createState() => _ShelfPageState();
}

class _ShelfPageState extends ConsumerState<ShelfPage> {
  late Future<List<ShelfItem>> _shelf;

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    _shelf =
        ref.read(bootProvider.future).then((h) => h.api.shelfList());
  }

  Future<void> _remove(ShelfItem item) async {
    final handle = await ref.read(bootProvider.future);
    await handle.api.shelfRemove(item.nid);
    _load();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('书架')),
      body: FutureBuilder<List<ShelfItem>>(
        future: _shelf,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return Center(child: Text('加载失败：${snap.error}'));
          }
          final items = snap.data ?? [];
          if (items.isEmpty) {
            return const Center(
              child: Text('书架还是空的——在书籍详情页点「收藏」加入',
                  style: TextStyle(color: Colors.grey)),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => _load(),
            child: ListView.builder(
              itemCount: items.length,
              itemBuilder: (context, i) {
                final it = items[i];
                return ListTile(
                  title: Text(it.title),
                  subtitle: Text(it.genre != null
                      ? '${it.author} · ${it.genre}'
                      : it.author),
                  trailing: IconButton(
                    icon: const Icon(Icons.favorite),
                    tooltip: '移出书架',
                    onPressed: () => _remove(it),
                  ),
                  onTap: () => context.push('/book/${it.nid}'),
                );
              },
            ),
          );
        },
      ),
    );
  }
}

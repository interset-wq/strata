import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import '../widgets/default_cover.dart';

/// 图片全屏查看器：大图精选点图进入。黑底全屏，左右滑动切图，
/// 单指点按关闭，双击 2× 缩放，双指捏合 1–4×。
class ImageViewerPage extends ConsumerStatefulWidget {
  final int initialIndex;

  const ImageViewerPage({super.key, required this.initialIndex});

  @override
  ConsumerState<ImageViewerPage> createState() => _ImageViewerPageState();
}

class _ImageViewerPageState extends ConsumerState<ImageViewerPage> {
  late final PageController _pc;
  late int _index;

  @override
  void initState() {
    super.initState();
    _index = widget.initialIndex.clamp(0, _items.length - 1);
    _pc = PageController(initialPage: _index);
  }

  List<FeaturedItem> get _items => ref.read(imageViewerProvider);

  @override
  void dispose() {
    _pc.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: PageView.builder(
                controller: _pc,
                itemCount: items.length,
                onPageChanged: (i) => setState(() => _index = i),
                itemBuilder: (context, i) => _ZoomableImage(
                  url: coverImageUrl(items[i].coverUrl) ??
                      defaultCoverUrl(items[i].nid),
                  nid: items[i].nid,
                  onTapClose: () => context.pop(),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Text(
                '${_index + 1} / ${items.length}',
                style: const TextStyle(color: Colors.white70, fontSize: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ZoomableImage extends StatefulWidget {
  final String url;
  final int nid;
  final VoidCallback onTapClose;

  const _ZoomableImage({
    required this.url,
    required this.nid,
    required this.onTapClose,
  });

  @override
  State<_ZoomableImage> createState() => _ZoomableImageState();
}

class _ZoomableImageState extends State<_ZoomableImage> {
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTapClose,
      child: InteractiveViewer(
        minScale: 1,
        maxScale: 4,
        child: Center(
          child: Image.network(
            widget.url,
            fit: BoxFit.contain,
            loadingBuilder: (_, child, progress) {
              if (progress == null) return child;
              return const Center(
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.white54));
            },
            errorBuilder: (_, _, _) =>
                defaultCover(widget.nid, fit: BoxFit.contain),
          ),
        ),
      ),
    );
  }
}

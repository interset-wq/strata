import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/providers.dart';
import '../data/api/strata_api.dart';
import 'banner_carousel.dart';
import 'default_cover.dart';

/// 大图卡：banner cut 成品图（CDN 居中裁切 750×430），按原生比例零裁切；
/// 点图进全屏查看器（在 items 列表内滑动），点文字进详情页。
/// 首页"大图精选"与"更多" gallery 共用。
class BannerLargeCard extends ConsumerStatefulWidget {
  final FeaturedItem item;
  final int index;
  final List<FeaturedItem> items;

  const BannerLargeCard({
    super.key,
    required this.item,
    required this.index,
    required this.items,
  });

  @override
  ConsumerState<BannerLargeCard> createState() => _BannerLargeCardState();
}

class _BannerLargeCardState extends ConsumerState<BannerLargeCard> {
  // 书籍封面是 3:4 竖图，塞进 16:9 容器会被裁成一条——
  // banner 源图 404 时只给占位容器，不做封面兜底。
  bool _bannerFailed = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final item = widget.item;
    final placeholder = ColoredBox(
      color: scheme.primary.withValues(alpha: .06),
      child: Center(
        child: Icon(Icons.image_not_supported_outlined,
            size: 36, color: scheme.outline),
      ),
    );

    return Container(
      margin: const EdgeInsets.fromLTRB(16, 6, 16, 6),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.outline.withValues(alpha: .25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius:
                const BorderRadius.vertical(top: Radius.circular(12)),
            child: AspectRatio(
              // cut 成品图（750×430），按原生比例零裁切。
              aspectRatio: bannerCutAspect,
              child: GestureDetector(
                onTap: () {
                  ref.read(imageViewerProvider.notifier).state = widget.items;
                  context.push('/image-viewer/${widget.index}');
                },
                child: _bannerFailed
                    ? placeholder
                    : ColoredBox(
                        color: scheme.primary.withValues(alpha: .1),
                        child: Image.network(
                          bannerCutUrl(item.nid),
                          fit: BoxFit.cover,
                          loadingBuilder: coverLoadingBuilder,
                          errorBuilder: (_, _, _) {
                            setState(() => _bannerFailed = true);
                            return placeholder;
                          },
                        ),
                      ),
              ),
            ),
          ),
          InkWell(
            onTap: () => context.push('/book/${item.nid}'),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(item.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: scheme.onSurface)),
                  const SizedBox(height: 3),
                  Text(item.author,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style:
                          TextStyle(fontSize: 11, color: scheme.secondary)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

#!/usr/bin/env python3
"""Create a non-destructive learning candidate from a completed work record."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-dir', required=True, help='显式指定已确认的计划目录，不推断宿主当前计划')
    parser.add_argument('--source', default='progress.md', help='计划内来源文件；默认 progress.md')
    parser.add_argument('--name', help='本轮候选名称，仅字母、数字、点、下划线和连字符；默认生成时间戳')
    args = parser.parse_args()
    try:
        plan_dir = Path(args.plan_dir).expanduser().resolve()
        source = (plan_dir / args.source).resolve()
        if plan_dir not in source.parents or not source.is_file():
            raise RuntimeError('来源必须是计划目录内已有的文件。')
        if not source.read_text(encoding='utf-8').strip():
            raise RuntimeError('来源文件为空，无法定位已完成工作的证据。')
        name = args.name if args.name is not None else datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9._-]*', name):
            raise RuntimeError('候选名称无效；请使用字母、数字、点、下划线和连字符，且不能以点开头。')
        target = plan_dir / f'learning_candidate-{name}.md'
        if target.exists():
            raise RuntimeError(f'候选已存在，拒绝覆盖：{target}')
        template = Path(__file__).resolve().parent.parent / 'templates/learning-candidate.md'
        text = template.read_text(encoding='utf-8')
        text = text.replace('[PLAN_ID]', plan_dir.name)
        text = text.replace('[SOURCE_PATH]', str(source))
        text = text.replace('[DATE]', date.today().isoformat())
        with target.open('x', encoding='utf-8') as handle:
            handle.write(text)
        print(f'已创建经验回流候选：{target}')
        print('状态为 proposed；用户明确批准前不得修改任何目标层。')
    except (OSError, RuntimeError) as exc:
        print(f'[dispatch-ai-loop-workflow] {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

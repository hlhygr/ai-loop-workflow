#!/usr/bin/env python3
"""Validate a test execution HTML report independently of plan completion."""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
from html.parser import HTMLParser
from typing import Callable, Dict, List, Optional, Tuple


TEST_RESULT_FIELDS = ('PASS', 'FAIL', 'BLOCKED', 'NOT_RUN')


TEST_REPORT_SECTIONS = (
    'scope',
    'environment',
    'cases',
    'findings',
    'data-state',
    'authorization',
)


VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class PlanError(RuntimeError):
    pass


class TestReportParser(HTMLParser):
    """Collect the machine-readable contract from a test execution report."""

    def __init__(
        self, text_is_visible: Optional[Callable[[List[Dict[str, object]]], bool]] = None
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.text_is_visible = text_is_visible
        self.stack: List[str] = []
        self.hidden_stack: List[bool] = []
        self.node_stack: List[Dict[str, object]] = []
        self.critical_paths: List[Tuple[str, List[Dict[str, object]]]] = []
        self.doctype_html = 0
        self.html_start_count = 0
        self.html_end_count = 0
        self.meta_charset_count = 0
        self.format_marker_count = 0
        self.sections: Dict[str, List[str]] = {}
        self.active_sections: List[Tuple[str, str, int, List[str]]] = []
        self.rows: List[Dict[str, object]] = []
        self.current_row: Optional[Dict[str, object]] = None
        self.current_field: Optional[Tuple[List[str], int, List[str]]] = None
        self.visible_counts: Dict[str, List[str]] = {}
        self.current_count: Optional[Tuple[str, int, List[str], bool]] = None
        self.external_resources: List[str] = []
        self.script_chunks: List[str] = []
        self.style_chunks: List[str] = []
        self.in_script = False
        self.in_style = False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attr = {name.lower(): (value or '') for name, value in attrs}
        inline_style = attr.get('style', '').replace(' ', '').lower()
        hidden = (
            (self.hidden_stack[-1] if self.hidden_stack else False)
            or 'hidden' in attr
            or attr.get('aria-hidden', '').lower() == 'true'
            or 'display:none' in inline_style
            or 'visibility:hidden' in inline_style
        )
        node: Dict[str, object] = {'tag': tag, 'attrs': attr, 'hidden': hidden}
        if tag not in VOID_TAGS:
            self.stack.append(tag)
            self.hidden_stack.append(hidden)
            self.node_stack.append(node)
        depth = len(self.stack)
        if tag == 'html':
            self.html_start_count += 1
        if tag == 'meta':
            if attr.get('charset', '').strip().lower() == 'utf-8':
                self.meta_charset_count += 1
            if (
                attr.get('name', '').strip().lower() == 'ai-loop-test-report'
                and attr.get('content', '').strip().lower() == 'v1'
            ):
                self.format_marker_count += 1
        section = attr.get('data-report-section', '').strip().lower()
        if section:
            self.active_sections.append((section, tag, depth, []))
            self.critical_paths.append((f'章节 {section}', [*self.node_stack]))
        case_id = attr.get('data-case-id', '').strip()
        if case_id:
            self.critical_paths.append((f'用例 {case_id}', [*self.node_stack]))
        if tag == 'tr' and attr.get('data-status'):
            self.current_row = {
                'case_id': attr.get('data-case-id', '').strip(),
                'status': attr.get('data-status', '').strip().upper(),
                'fields': {},
            }
        fields = attr.get('data-fields', '').split()
        if tag == 'td' and self.current_row is not None and fields:
            self.current_field = (fields, depth, [])
            self.critical_paths.append((f'用例字段 {"/".join(fields)}', [*self.node_stack]))
        count_name = attr.get('data-result-count', '').strip().upper()
        if count_name:
            self.current_count = (count_name, depth, [], hidden or tag != 'strong')
            self.critical_paths.append((f'统计 {count_name}', [*self.node_stack]))
        src = attr.get('src', '').strip()
        if src and not src.lower().startswith('data:'):
            self.external_resources.append(src)
        srcset = attr.get('srcset', '').strip()
        if srcset and not srcset.lower().startswith('data:'):
            self.external_resources.append(srcset)
        if tag == 'link' and attr.get('href', '').strip():
            self.external_resources.append(attr['href'])
        if tag in ('image', 'use'):
            href = (attr.get('href', '') or attr.get('xlink:href', '')).strip()
            if href and not href.lower().startswith('data:') and not href.startswith('#'):
                self.external_resources.append(href)
        for resource_attr in ('data', 'poster'):
            value = attr.get(resource_attr, '').strip()
            if value and not value.lower().startswith('data:'):
                self.external_resources.append(value)
        if tag == 'base' and attr.get('href', '').strip():
            self.external_resources.append(attr['href'])
        if tag in ('form', 'button', 'input') and (
            attr.get('action', '').strip() or attr.get('formaction', '').strip()
        ):
            self.external_resources.append(
                attr.get('action', '').strip() or attr.get('formaction', '').strip()
            )
        if tag == 'meta' and attr.get('http-equiv', '').strip().lower() == 'refresh':
            self.external_resources.append(attr.get('content', '') or '<meta refresh>')
        style_attr = attr.get('style', '')
        if style_attr:
            self.style_chunks.append(style_attr)
        if tag == 'script':
            self.in_script = True
        if tag == 'style':
            self.in_style = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        depth = len(self.stack)
        if self.current_field and tag == 'td' and self.current_field[1] == depth:
            names, _, chunks = self.current_field
            text_value = ' '.join(''.join(chunks).split())
            fields = self.current_row['fields'] if self.current_row else {}
            for name in names:
                fields[name.lower()] = text_value
            self.current_field = None
        if self.current_count and self.current_count[1] == depth:
            name, _, chunks, hidden = self.current_count
            value = '' if hidden else ' '.join(''.join(chunks).split())
            self.visible_counts.setdefault(name, []).append(value)
            self.current_count = None
        completed_sections = [
            item for item in self.active_sections
            if item[1] == tag and item[2] == depth
        ]
        for name, _, _, chunks in completed_sections:
            self.sections.setdefault(name, []).append(' '.join(''.join(chunks).split()))
            self.active_sections.remove((name, tag, depth, chunks))
        if tag == 'tr' and self.current_row is not None:
            self.rows.append(self.current_row)
            self.current_row = None
            self.current_field = None
        if tag == 'script':
            self.in_script = False
        if tag == 'style':
            self.in_style = False
        if tag == 'html':
            self.html_end_count += 1
        if self.stack:
            self.stack.pop()
        if self.hidden_stack:
            self.hidden_stack.pop()
        if self.node_stack:
            self.node_stack.pop()

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.script_chunks.append(data)
        if self.in_style:
            self.style_chunks.append(data)
        # Resource discovery always sees script/style text; report values do not.
        if self.in_script or self.in_style:
            return
        if self.text_is_visible is not None and not self.text_is_visible(self.node_stack):
            return
        for _, _, _, chunks in self.active_sections:
            chunks.append(data)
        if self.current_field:
            self.current_field[2].append(data)
        if self.current_count:
            self.current_count[2].append(data)

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() == 'doctype html':
            self.doctype_html += 1


def css_without_print_media(css_text: str) -> str:
    while match := re.search(r'@media\s+print\s*\{', css_text, re.IGNORECASE):
        brace_start = css_text.find('{', match.start())
        depth = 0
        for index in range(brace_start, len(css_text)):
            if css_text[index] == '{':
                depth += 1
            elif css_text[index] == '}':
                depth -= 1
                if depth == 0:
                    css_text = css_text[:match.start()] + css_text[index + 1:]
                    break
        else:
            raise PlanError('测试执行交付的 HTML report 中 print 样式块未闭合。')
    return css_text


def css_declarations(text: str) -> Dict[str, Tuple[str, bool]]:
    declarations: Dict[str, Tuple[str, bool]] = {}
    for part in text.split(';'):
        if ':' not in part:
            continue
        name, value = part.split(':', 1)
        name = name.strip().lower()
        if name in ('display', 'visibility'):
            value = value.strip().lower()
            important = value.endswith('!important')
            if important:
                value = value[:-10].strip()
            if name not in declarations or important or not declarations[name][1]:
                declarations[name] = (value, important)
    return declarations


def selector_parts(selector: str) -> Tuple[List[Tuple[str, set[str], set[str]]], int]:
    parts = []
    specificity = 0
    for token in selector.split():
        if not re.fullmatch(r'(?:[a-zA-Z][\w-]*|\*)?(?:[.#][a-zA-Z_][\w-]*)*', token) or not token:
            raise PlanError(
                '测试执行交付的 HTML report 含无法静态验证可见性的 CSS 选择器：'
                + selector + '；请改用标签、类、ID 或后代选择器并人工核对报告。'
            )
        tag_match = re.match(r'[a-zA-Z][\w-]*|\*', token)
        tag = tag_match.group(0).lower() if tag_match else ''
        classes = set(re.findall(r'\.([a-zA-Z_][\w-]*)', token))
        ids = set(re.findall(r'#([a-zA-Z_][\w-]*)', token))
        specificity += len(ids) * 100 + len(classes) * 10 + (1 if tag and tag != '*' else 0)
        parts.append((tag, classes, ids))
    return parts, specificity


def selector_matches(parts: List[Tuple[str, set[str], set[str]]], path: List[Dict[str, object]]) -> bool:
    position = len(path) - 1
    for part_number, (tag, classes, ids) in enumerate(reversed(parts)):
        while position >= 0:
            node = path[position]
            attrs = node['attrs']
            if (
                (not tag or tag == '*' or node['tag'] == tag)
                and classes.issubset(set(attrs.get('class', '').split()))
                and (not ids or ids == {attrs.get('id', '')})
            ):
                position -= 1
                break
            if part_number == 0:
                return False
            position -= 1
        else:
            return False
    return True


def validate_critical_visibility(
    parser: TestReportParser, screen_css: str
) -> Callable[[List[Dict[str, object]]], bool]:
    css = re.sub(r'/\*.*?\*/', '', screen_css, flags=re.DOTALL)
    if not re.search(r'\b(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\b', css, re.IGNORECASE):
        # No stylesheet hide to resolve, but inline/attribute hiding still applies.
        css = ''
    while match := re.search(r'@(?:media|supports|container)\b[^{}]*\{', css, re.IGNORECASE):
        depth = 0
        for end in range(css.find('{', match.start()), len(css)):
            if css[end] == '{':
                depth += 1
            elif css[end] == '}':
                depth -= 1
                if depth == 0:
                    block = css[match.start():end + 1]
                    if re.search(r'\b(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))\b', block, re.IGNORECASE):
                        raise PlanError('测试执行交付的 HTML report 含条件隐藏样式；请改用静态样式并人工核对报告。')
                    css = css[:match.start()] + css[end + 1:]
                    break
        else:
            raise PlanError('测试执行交付的 HTML report 条件样式块未闭合，无法验证可见性。')
    rules = []
    for match in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        declarations = css_declarations(match.group(2))
        if not declarations:
            continue
        for selector in match.group(1).split(','):
            parts, specificity = selector_parts(selector.strip())
            rules.append((parts, specificity, declarations))
    def text_is_visible(path: List[Dict[str, object]]) -> bool:
        for index, node in enumerate(path):
            if node['hidden']:
                return False
            node_path = path[:index + 1]
            winning: Dict[str, Tuple[Tuple[int, int, int], str]] = {}
            for order, (parts, specificity, declarations) in enumerate(rules):
                if not selector_matches(parts, node_path):
                    continue
                for name, (value, important) in declarations.items():
                    rank = (int(important), specificity, order)
                    if name not in winning or rank >= winning[name][0]:
                        winning[name] = (rank, value)
            inline = css_declarations(str(node['attrs'].get('style', '')))
            for name, (value, important) in inline.items():
                rank = (int(important), 1000, len(rules))
                if name not in winning or rank >= winning[name][0]:
                    winning[name] = (rank, value)
            if winning.get('display', (None, None))[1] == 'none' or winning.get('visibility', (None, None))[1] in ('hidden', 'collapse'):
                return False
        return True

    for label, path in parser.critical_paths:
        if not text_is_visible(path):
            raise PlanError(f'测试执行交付的 HTML report 必要节点或祖先被样式隐藏：{label}。')
    return text_is_visible


def validate_report(plan_dir: Path, checkpoint: Dict[str, str]) -> None:
    report_value = checkpoint.get('HTML report', '')
    if not report_value:
        raise PlanError('测试执行交付缺少 HTML report 绝对路径。')
    report_path = Path(report_value).expanduser()
    if not report_path.is_absolute():
        raise PlanError('测试执行交付的 HTML report 必须使用绝对路径。')
    try:
        report_path.resolve().relative_to(plan_dir.resolve())
    except ValueError as exc:
        raise PlanError('测试执行交付的 HTML report 必须位于当前计划目录内。') from exc
    if report_path.is_symlink() or not report_path.is_file():
        raise PlanError('测试执行交付的 HTML report 不存在或不是普通文件。')
    if report_path.stat().st_size == 0:
        raise PlanError('测试执行交付的 HTML report 不能为空文件。')
    try:
        report_text = report_path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise PlanError(f'测试执行交付的 HTML report 必须是可读取的 UTF-8 文件：{exc}') from exc
    parser = TestReportParser()
    try:
        parser.feed(report_text)
        parser.close()
    except Exception as exc:
        raise PlanError(f'测试执行交付的 HTML report 无法解析：{exc}') from exc
    if parser.doctype_html != 1 or parser.html_start_count != 1 or parser.html_end_count != 1:
        raise PlanError(
            '测试执行交付的 HTML report 缺少 HTML5 doctype 或完整 html 根节点。'
        )
    if parser.meta_charset_count != 1:
        raise PlanError('测试执行交付的 HTML report 缺少 UTF-8 charset 声明。')
    if parser.format_marker_count != 1:
        raise PlanError('测试执行交付的 HTML report 缺少 ai-loop-test-report=v1 标记。')
    css_text = '\n'.join(parser.style_chunks)
    screen_css = css_without_print_media(css_text)
    css_urls = re.findall(r'url\(\s*["\']?([^"\')\s]+)', css_text, re.IGNORECASE)
    non_inline_css_urls = [
        value for value in css_urls
        if not value.lower().startswith('data:') and not value.startswith('#')
    ]
    script_text = '\n'.join(parser.script_chunks)
    network_script_patterns = (
        r'\bfetch\s*\(',
        r'\bXMLHttpRequest\b',
        r'\bWebSocket\s*\(',
        r'\bEventSource\s*\(',
        r'\baxios\b',
        r'\bnavigator\.sendBeacon\s*\(',
        r'\bimport\s*(?:\([^)]*\)|[^;]*\bfrom\s*)["\'](?:https?:)?//',
        r'["\'](?:https?:)?//',
        r'["\'](?:/|\./|\.\./)[^"\']*["\']',
    )
    if (
        parser.external_resources
        or non_inline_css_urls
        or re.search(r'@import\s+', css_text, re.IGNORECASE)
        or any(re.search(pattern, script_text) for pattern in network_script_patterns)
    ):
        raise PlanError('测试执行交付的 HTML report 引用了外部资源，不是自包含文件。')
    text_is_visible = validate_critical_visibility(parser, screen_css)
    # Reuse the same parser contract, now counting only visible text fragments.
    # CSS may appear after the content, so visibility is resolved after discovery.
    parser = TestReportParser(text_is_visible=text_is_visible)
    parser.feed(report_text)
    parser.close()
    invalid_report_sections = [
        name for name in TEST_REPORT_SECTIONS
        if len(parser.sections.get(name, [])) != 1
        or not parser.sections[name][0].strip()
    ]
    if invalid_report_sections:
        raise PlanError(
            '测试执行交付的 HTML report 必要章节缺失、重复或为空：'
            + '、'.join(invalid_report_sections)
            + '。'
        )
    try:
        planned_cases = int(checkpoint.get('Planned cases', ''))
        expected_counts = {
            field: int(checkpoint.get(field, ''))
            for field in TEST_RESULT_FIELDS
        }
    except ValueError as exc:
        raise PlanError(
            '测试执行交付必须在 checkpoint 写入整数 Planned cases、'
            'PASS、FAIL、BLOCKED、NOT_RUN。'
        ) from exc
    if planned_cases < 1 or any(value < 0 for value in expected_counts.values()):
        raise PlanError('测试执行交付的用例数与四类结果计数不能为负，计划数必须大于 0。')
    if sum(expected_counts.values()) != planned_cases:
        raise PlanError('测试执行交付的四类结果计数之和与 Planned cases 不一致。')
    required_case_fields = ('expected', 'actual', 'evidence', 'state', 'cleanup')
    case_ids = []
    report_statuses = []
    for row in parser.rows:
        case_id = str(row.get('case_id', '')).strip()
        row_status = str(row.get('status', '')).strip()
        fields = row.get('fields', {})
        if not case_id:
            raise PlanError('测试执行交付的 HTML 存在缺少唯一用例 ID 的逐例记录。')
        if case_id in case_ids:
            raise PlanError(f'测试执行交付的 HTML 存在重复用例 ID：{case_id}。')
        if row_status not in TEST_RESULT_FIELDS:
            raise PlanError(f'测试执行交付的 HTML 用例 {case_id} 结果状态无效。')
        missing_case_fields = [
            field for field in required_case_fields
            if not isinstance(fields, dict) or not str(fields.get(field, '')).strip()
        ]
        if missing_case_fields:
            raise PlanError(
                f'测试执行交付的 HTML 用例 {case_id} 缺少非空字段：'
                + '、'.join(missing_case_fields)
                + '。'
            )
        case_ids.append(case_id)
        report_statuses.append(row_status)
    actual_counts = {
        field: report_statuses.count(field)
        for field in TEST_RESULT_FIELDS
    }
    if len(report_statuses) != planned_cases:
        raise PlanError('测试执行交付的 HTML 逐例记录数与 Planned cases 不一致。')
    if actual_counts != expected_counts:
        raise PlanError('测试执行交付的 HTML 四类逐例计数与 delivery checkpoint 不一致。')
    expected_visible_counts = {'PLANNED': planned_cases, **expected_counts}
    try:
        visible_counts = {
            name: int(parser.visible_counts[name][0])
            for name in expected_visible_counts
        }
    except (KeyError, IndexError, ValueError) as exc:
        raise PlanError('测试执行交付的 HTML 缺少可机器核对的可见统计。') from exc
    if any(len(parser.visible_counts.get(name, [])) != 1 for name in expected_visible_counts):
        raise PlanError('测试执行交付的 HTML 可见统计必须每类恰好一个。')
    if visible_counts != expected_visible_counts:
        raise PlanError('测试执行交付的 HTML 可见统计与 delivery checkpoint 不一致。')

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-dir', help='已有计划目录；省略时必须显式提供 --report')
    parser.add_argument('--report', help='报告路径；无计划时相对于当前目录，有计划时相对于计划目录')
    parser.add_argument('--planned-cases', type=int, required=True)
    for field in TEST_RESULT_FIELDS:
        parser.add_argument('--' + field.lower().replace('_', '-') + '-count', type=int, required=True)
    args = parser.parse_args()
    if not args.plan_dir and not args.report:
        parser.error('没有 --plan-dir 时必须显式提供 --report。')
    directory = Path(args.plan_dir).expanduser().resolve() if args.plan_dir else Path.cwd()
    report = Path(args.report).expanduser() if args.report else Path('test-execution-report.html')
    if not report.is_absolute():
        report = directory / report
    if not args.plan_dir:
        directory = report.parent.resolve()
    checkpoint = {'HTML report': str(report), 'Planned cases': str(args.planned_cases)}
    checkpoint.update({field: str(getattr(args, field.lower() + '_count')) for field in TEST_RESULT_FIELDS})
    try:
        validate_report(directory, checkpoint)
    except (OSError, PlanError) as exc:
        print(f'[AI Loop test report] {exc}', file=sys.stderr)
        return 1
    print(f'测试执行报告校验通过：{checkpoint["HTML report"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

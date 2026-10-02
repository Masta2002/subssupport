import re

from .baseparser import BaseParser, ParseError


class AssParser(BaseParser):
    """Advanced SubStation Alpha / SubStation Alpha (.ass/.ssa), dialogue lines of the [Events] section."""
    format = "ASS/SSA"
    parsing = ('.ass', '.ssa')

    # vector drawings ({\p1}...{\p0}) are not text
    _DRAWING = re.compile(r'\{[^}]*\\p[1-9][^}]*\}.*?(?=\{[^}]*\\p0|$)')

    def _removeTags(self, text):
        text = re.sub(r'\{[^}]*\}', '', text)  # override codes like {\an8}, {\i1}
        return text.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ').strip()

    def _getStyle(self, text, style):
        if re.search(r'\{[^}]*\\i1', text):
            style = 'italic'
        elif re.search(r'\{[^}]*\\b1', text):
            style = 'bold'
        elif style not in ('italic', 'bold'):
            style = ''
        # rowParse: the style continues on the next row until it is closed
        if re.search(r'\{[^}]*\\(?:i0|b0|r)', text):
            return style, ''
        return style, style

    @staticmethod
    def _time(value):
        h, m, s = value.strip().split(':')
        return int(round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000))

    def _parse(self, text, fps):
        fields = ['layer', 'start', 'end', 'style', 'name', 'marginl', 'marginr', 'marginv', 'effect', 'text']
        subs = []
        events = False
        for line in text.splitlines():
            line = line.strip()
            if line.startswith('['):
                events = line.lower() == '[events]'
            elif events and line.lower().startswith('format:'):
                fields = [f.strip().lower() for f in line[7:].split(',')]
            elif events and line.lower().startswith('dialogue:'):
                values = line[9:].split(',', len(fields) - 1)
                if len(values) != len(fields):
                    continue
                event = dict(zip(fields, values))
                try:
                    start, end = self._time(event['start']), self._time(event['end'])
                except (KeyError, ValueError) as e:
                    raise ParseError("invalid dialogue line: %s (%s)" % (line, e))
                subText = self._DRAWING.sub('', event.get('text', ''))
                subText = subText.replace('\\N', '\n').replace('\\n', '\n')
                if self._removeTags(subText):
                    subs.append((start, end, subText))
        subs.sort(key=lambda sub: sub[0])  # ass files are not required to be sorted
        return [self.createSub(text, start, end) for start, end, text in subs]


parserClass = AssParser

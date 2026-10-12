import re
def parse(text): return {m.group(1):m.group(3)+"\n" for m in re.finditer(r"### (\S+)\n```(\w*)\n(.*?)\n```",text,re.S)}

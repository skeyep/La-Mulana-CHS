"""Apply reviewed color ranges without changing source anchors or Chinese text."""
COL = 0x4a

def range_chunks(text, base_color, adjustments, segment_index):
    selected = sorted((a for a in adjustments if a['kind']=='range' and a['source_segment_index']==segment_index), key=lambda a:a['start'])
    chunks=[]; cursor=0
    for a in selected:
        start,end=a['start'],a['end']
        assert cursor<=start<end<=len(text) and text[start:end]==a['text'], a
        color=a['color']; assert len(color)==3 and all(type(v) is int and 0<=v<=255 for v in color)
        if cursor<start: chunks.append((text[cursor:start],list(base_color)))
        chunks.append((text[start:end],color)); cursor=end
    if cursor<len(text): chunks.append((text[cursor:],list(base_color)))
    return chunks

def apply_colors(record, compiled, removed_layout=()):
    adjustments=record.get('color_adjustments',[])
    if not adjustments:return compiled,[]
    replacements={a['source_control_segment_index']:a for a in adjustments if a['kind']=='replace-control'}
    assert len(replacements)==sum(a['kind']=='replace-control' for a in adjustments)
    runs={r['source_segment_index']:r for r in record['translation_runs']}
    result=[]; cursor=0; color=[0,0,0]; reports=[]
    seen=set()
    for i,s in enumerate(record['baseline']['source_segments']):
        if i in removed_layout:
            assert s['kind']=='layout' and s['tokens']==[32]
            continue
        if s['kind']=='glyph_run':
            text=runs[i]['zh']; tokens=compiled[cursor:cursor+len(text)]; cursor+=len(text)
            assert len(tokens)==len(text)
            offset=0; painted=color[:]
            for piece,chosen in range_chunks(text,color,adjustments,i):
                if painted!=chosen:result.extend([COL,*chosen]);painted=chosen
                result.extend(tokens[offset:offset+len(piece)]);offset+=len(piece)
            assert offset==len(tokens)
            if painted!=color:result.extend([COL,*color])
            for a in adjustments:
                if a['kind']=='range' and a['source_segment_index']==i:reports.append(a);seen.add(id(a))
        else:
            tokens=s['tokens'][:]
            assert compiled[cursor:cursor+len(tokens)]==tokens,(record['block_index'],i)
            cursor+=len(tokens)
            if i in replacements:
                a=replacements[i];assert tokens==[COL,*a['from_color']]
                tokens=[COL,*a['color']];reports.append(a);seen.add(id(a))
            result.extend(tokens)
            if tokens[0]==COL:color=tokens[1:]
    assert cursor==len(compiled) and len(seen)==len(adjustments)
    return result,reports

def preview(record):
    runs={r['source_segment_index']:r['zh'] for r in record['translation_runs']}
    replacements={a['source_control_segment_index']:a for a in record.get('color_adjustments',[]) if a['kind']=='replace-control'}
    pieces=[]; color=[0,0,0]
    def mark(c):return '{COL '+','.join(map(str,c))+'}'
    for i,s in enumerate(record['baseline']['source_segments']):
        if s['kind']=='glyph_run':
            painted=color[:]
            for text,chosen in range_chunks(runs[i],color,record.get('color_adjustments',[]),i):
                if painted!=chosen:pieces.append(mark(chosen));painted=chosen
                pieces.append(text)
            if painted!=color:pieces.append(mark(color))
        elif s['kind']=='layout':pieces.append(s['text'])
        else:
            name=s.get('name_from_public_decoder','CMD');args=s.get('arguments',[])
            if i in replacements:args=replacements[i]['color']
            if name=='COL':color=args[:]
            pieces.append('{'+name+(' '+','.join(map(str,args)) if args else '')+'}')
    return ''.join(pieces)

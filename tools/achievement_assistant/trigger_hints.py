"""Player-facing trigger hints, bound to installed selectors and canonical names."""
import json

def ranges(values):
    result = []
    for value in sorted(set(values)):
        if result and value == result[-1][1] + 1:
            result[-1][1] = value
        else:
            result.append([value, value])
    return result

def range_text(intervals):
    return '、'.join(str(a) if a == b else f'{a}—{b}' for a, b in intervals)

def enrich(root, dialogues, mails):
    parsed = json.loads((root/'localization/source/lm1/parsed/data/language/jp/script_code.json').read_text(encoding='utf-8'))
    commands = lambda n: [s['arguments'] for s in parsed['blocks'][n]['segments'] if s.get('opcode') == 78]
    item_doc = json.loads((root/'localization/translations/items-software.json').read_text(encoding='utf-8'))
    item_row = next(r for r in item_doc['records'] if r['block_index'] == 1)
    items = {r['source_segment_index']//2:r['zh'] for r in item_row['translation_runs']}
    bounds = {484:(0,70),1080:(71,140),1081:(141,255),1019:(141,255),485:(56,120),1082:(121,199),1083:(200,255)}
    for d in dialogues:
        intervals = []
        if any(r[0] == 4 for r in d['rules']):
            values = []
            for master in d['roots']:
                score_table = commands(master)[0][2]
                lo, hi = bounds[master]
                values.extend(n for n in range(lo,hi+1) if not any(a<=n<=b for a,b,*_ in commands(score_table)))
            intervals = ranges(values)
            d['note'] = '随机对白；流程点数 '+range_text(intervals)+'时反复交谈。'
            # Effective windows exclude fixed-score dialogue, including Xelpud 200+.
            d['rules'] = [r for r in d['rules'] if r[0]!=5]+[[5,intervals[0][0],intervals[-1][1]]]
        d['random_windows'] = intervals
        held = next((r for r in d['rules'] if r[0]==3),None)
        if held:
            name = items[held[1]]
            d['title'] = ('充能的' if held[1]==25 else '')+name
            d['note'] = '装备'+name+'后交谈。'
            if held[1]==25:d['note'] = '时之灯充能后，装备时之灯交谈。'
            if held[1]==31:d['note'] += '须在变成孕妇像之前。'
        specific={364:'开局首次进入地上的长老帐篷交谈。',
                  366:'首次见过长老后，离开帐篷再返回交谈。',
                  396:'唤醒穆尔并听完第一次对话后，流程点数≥56，再返回交谈。',
                  400:'首次进入无限回廊后，返回穆尔处交谈。',
                  405:'首次进入产声之碑后，返回穆尔处交谈。',
                  406:'听完穆尔介绍产声之碑的神明后，立即再交谈。',
                  367:'收到18号召回邮件后回村交谈；须在击败第2位守卫前返回。',
                  375:'收到25号邮件后，回村与长老交谈。',
                  376:'唤醒穆尔后，回村与长老交谈。',
                  377:'收到43号邮件并回村回应后，按长老要求处理电脑。',
                  370:'在圣母之祠发现暂时无法取得的日记宝箱后，回村找长老帮忙。',
                  371:'取得日记后，回村与长老交谈。',
                  372:'取得穆拉纳护符后，立即再与长老交谈。',
                  409:'取得贤者陶笛后，经过月光圣殿的月之金字塔玄室，再返回穆尔处交谈。',
                  1049:'取得危险泳装后，穿上它与长老交谈。',
                  417:'地狱圣堂入口开启后，返回穆尔处交谈。',
                  418:'通关地狱圣堂取得危险泳装后，返回穆尔处交谈。'}
        if d['block'] in specific:d['note']=specific[d['block']]
        d['short_note']=d['note'] if len(d['note'])<=42 else d['note'].split('；')[0]+'。'
    # Each location is taken from the actual object's container, translated with the room table.
    room_doc=json.loads((root/'localization/translations/room-names.json').read_text(encoding='utf-8'))
    names={r['source_text']:r['zh'] for row in room_doc['records'] for r in row['translation_runs']}
    # RCD editor labels differ from the room-name resource at these two locations.
    names['地表']='地上'
    names['シヴァの十字架']=names['シヴァの十字壁画']
    names['迷いからの扉']=names['エデンからの扉']
    names['産声の碑：下']=names['産声の碑']+'下部'
    names['冥界の大列柱室']='冥界大列柱室'
    names['LA-MULANA遺跡入口']=names['ＬＡ-ＭＵＬＡＮＡ遺跡入口']
    world=json.loads((root/'localization/context/world.json').read_text(encoding='utf-8'))
    def location(path):
        c=path['container'];z=world['zones'][c['zone_index']]
        zone=names.get(z['name_raw'],z['name_raw'])
        if c['scope']=='zone':return zone
        if c['scope']=='room':
            screens=z['rooms'][c['room_index']]['screens']
            rooms=list(dict.fromkeys(names.get(s['name_raw'],s['name_raw']) for s in screens))
            return zone+'·'+'／'.join(rooms)
        screen=z['rooms'][c['room_index']]['screens'][c['screen_index']]
        raw=screen['name_raw'];name=names.get(raw,raw)
        if c['zone_index']==8 and raw=='０':name=names['第１無限回廊']
        if raw=='地図':name='地图所在画面'
        return zone+'·'+name
    conditions={0:'启用长老邮箱后',1:'离村探索时',2:'取得手持扫描器后',3:'启用长老邮箱后',4:'启用长老邮箱后',
        5:'取得指引之门的生命宝珠后',6:'在指引之门消灭100只蝙蝠后',8:'取得圣杯后',
        10:'取得对应区域的安卡宝石后',11:'靠近单向门左侧后',12:'启用长老邮箱后',13:'启用长老邮箱后',
        14:'启用长老邮箱后',15:'启用长老邮箱后',16:'取得赫尔墨斯之靴后',17:'取得铜镜后',
        18:'击败第1位守卫后、第2位前',19:'收到18号召回邮件后回村找长老，离开帐篷后',
        20:'启用长老邮箱后',21:'取得起始之印后',22:'启用长老邮箱后',23:'启用长老邮箱后',
        24:'与妖精女王交谈后',25:'击败第2位守卫后、第3位前',26:'启用长老邮箱后',
        27:'读取两处里侧圣杯碑后',28:'启用长老邮箱后',29:'启用长老邮箱后',30:'取得钩爪后',31:'取得羽毛后',
        32:'取得时之灯后',33:'启用长老邮箱后',34:'取得炸弹后',35:'已收邮件总数达到30后',
        40:'流程点数≥140',41:'流程点数≥180，已收到40号《真闲啊》',42:'流程点数≥200',
        43:'击败第4位守卫后、第5位前，且尚未推进升级电脑的剧情'}
    for m in mails:
        locs=list(dict.fromkeys(location(p) for p in m['paths']))
        m['trigger_locations']=locs
        n=m['number']
        if n in conditions:m['note']=conditions[n]+'；到'+('或'.join(locs))+'等收信。'
        if n==7:m['note']='；'.join('取得'+name+'→'+loc for name,loc in zip(['龙骨','无限之钥','胡椒','蛇杖'],locs))+'。任选对应路线等收信。'
        if n==9:m['note']='；'.join('取得'+name+'→'+loc for name,loc in zip(['手里剑','风车手里剑','铁蒺藜'],locs))+'。任选对应路线等收信。'
        if n in [36,37]:m['note']=('尚未学会古代文字，未译石碑调查次数恰为'+('1' if n==36 else '5')+'时，在死灭之碑或里侧区域等收信；收信前不要继续增加调查次数。')
        if n in [38,39]:m['note']=('收集10款软件' if n==38 else '收集3款NIGORO游戏软件')+'后，在地上或主遗迹区域等收信。'
        if n==44:m['note']='取得龙骨→双连迷宫；胡椒→迷失之门；蛇杖→月光圣殿。向长老展示会触发物品提示的道具前，在对应区域等收信。'
        m['short_note']=conditions[n]+'；到'+locs[0].split('／')[0]+'等收信。' if n in conditions else m['note']
        short={7:'取得龙骨后，到双连迷宫·双子周壁等收信。',
               9:'取得手里剑后，到指引之门·勇气之厅等收信。',
               19:'收到18号后先找长老，再离开帐篷等信。',
               36:'学习古代文字前，调查第1处未译石碑后等信。',
               37:'学习古代文字前，调查第5处未译石碑后等信。',
               41:'流程点数≥180＋已收40号；去第3无限回廊等收信。',
               43:'击败第4位守卫后，升级电脑前；去巴尔瀑布等信。',
               44:'展示物品前，带龙骨去双连迷宫等信。'}
        if n in short:m['short_note']=short[n]
        if all(any(t['flag_index']==898 and t['value_raw_u8']==0 for t in p['test_operations']) for p in m['paths']):
            m['note']+='终战前可收取。'
    return {'items':items,'story':[commands(486),commands(480)],'score':[commands(488),commands(482)]}

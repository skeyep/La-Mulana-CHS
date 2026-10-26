"""Build read-only dialogue catalogue from canonical Chinese and original selectors."""
from pathlib import Path
import json
import re
from trigger_hints import enrich
from dialogue_routes import generate as generate_routes

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'localization/achievement-assistant'

def build():
    source = json.loads((ROOT/'localization/research/achievement-monitor-20261024/dialogue-flags.json').read_text(encoding='utf-8'))['jp']
    parsed = json.loads((ROOT/'localization/source/lm1/parsed/data/language/jp/script_code.json').read_text(encoding='utf-8'))
    commands = lambda n: [s['arguments'] for s in parsed['blocks'][n]['segments'] if s.get('opcode') == 78]
    contexts = {r['block_index']: r for r in json.loads((ROOT/'localization/context/block_contexts.json').read_text(encoding='utf-8'))['rows']}
    translations = {}
    canonical = {}
    for path in sorted((ROOT/'localization/translations').glob('*.json')):
        if 'reading' in path.name or 'validation' in path.name:
            continue
        doc = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(doc, dict):
            continue
        for row in doc.get('records', []):
            if 'translation_runs' in row:
                text = ''.join(r['zh'] for r in row['translation_runs'])
                if row['block_index'] in translations and translations[row['block_index']] != text:
                    raise ValueError(f'duplicate canonical block {row["block_index"]}: {path}')
                translations[row['block_index']] = text
                canonical[row['block_index']] = row
    # Approximate route position for item/story entries; score entries use their actual first interval.
    route = {364:0,366:2,986:14,367:28,375:42,392:49,393:50,396:56,376:57,
             398:65,399:70,397:80,400:90,401:100,403:115,377:115,404:130,
             388:138,408:138,389:140,409:142,369:100,370:145,371:150,372:151,
             987:152,405:165,406:175,414:202,415:203,416:205,417:245,418:260,1049:261,
             379:80,391:100,390:135,382:130,384:180,381:185,380:190,378:195,
             385:170,386:195,387:90,383:150}
    notes = {392:'初见穆尔时',393:'解除沉睡后立即交谈',396:'穆尔逐渐清醒时',
             398:'进入灼热洞窟后，取得冰之斗篷前',399:'进入死灭之碑后，永久点亮前',
             400:'探索无限回廊后',401:'发现双连迷宫升降台故障后，修好前',
             403:'升级笔记本后，扫描咒文软件墙前',404:'探索女神之塔后，到达塔顶圣杯点前',
             405:'探索产声之碑后',406:'接着询问产声之碑',397:'尝试攻击阿努比斯后',
             408:'装备女性像；变成孕妇像前',388:'装备女性像；变成孕妇像前',
             414:'击败八守卫后',415:'谈到父亲后立即再聊，推进寻找前',416:'寻找父亲的第一步之后',
             417:'开启地狱圣堂后',418:'通关地狱圣堂，带回衣服后',1049:'穿泳装与长老交谈',
             371:'取得父亲日记后',372:'取得穆拉纳护符后立即再聊',367:'收到长老召回邮件后',
             375:'收到沉睡之人相关邮件后',376:'唤醒穆尔后',377:'收到新电脑邮件后'}
    result = []
    mul_titles='初见穆尔|醒来与瓦吉特|还想睡|还是想睡|裁缝的女儿|阿努比斯与死者之书|灼热洞窟的熔岩|死灭之碑的黑暗|无限回廊|双连迷宫升降台|妖精女王|电脑与墙上的软件|女神之塔|产声之碑的神明|更多神明的故事|别叫醒我|女性像|贤者陶笛|解开全部谜题之后|遗迹消失之日|你会来救我吗|圣杯的隐藏力量|寻找父亲|父亲躲在哪里|与谜题无关的雕像|地狱圣堂|父亲的衣服|第一子|第二子|第三子|第四子|第五子|第六子|第七子|圣母衰弱的力量|遗迹文字里的数字|吃不下了|好大的东西|再睡一百年|从尾巴生吞|戴帽子的家伙|石地板太硬|落枕|戴眼镜的老头|纯真少女的梦话|全都揍一顿|睡着时别乱来|遗迹要塌了|笨蛋|身上压块石头|我很开心|汉堡包|续关的梦话|咬牙切齿|呼噜声|向本小姐低头'.split('|')
    elder_titles='初见长老|怎么还没进遗迹|只是太无聊|父亲的护符|父亲的日记|穆拉纳护符|第七子的使命|今天的风儿|还活着就好|沉睡之人的传说|真的有沉睡之人|新电脑|节德柱|小人人偶|勾玉|生命齿轮|充能的时之灯|腰包钥匙|龙骨|水晶骷髅|容器|胡椒|女性像|孕妇像|无限之钥|别打扰我玩游戏|探索得怎么样|正在写邮件|蛇杖|又输给第二关首领|又死在第二关|没在看奇怪东西|放弃第二关了|手持扫描器|村中传承的护符|天罚|温泉|这游戏提示太多|我是伟大的长老|肚子饿了|开场太长|玩动作游戏|想发财|遗迹旅游计划|我才是最终首领|家里的隐藏迷宫|会出续作吗|其实我是女孩子|做个鬼脸|想玩射击游戏|下载点数不够|没有游戏瘾|招揽外国游客|歇一会儿吧|写邮件写酸了|一直看着你|泳装与今天的风儿'.split('|')
    assert len(mul_titles)==56 and len(elder_titles)==57
    for src in source:
        block = int(src['block']); flag = src['flag']; ctx = contexts[block]
        rules = []; roots = []
        for path in ctx['static_contexts']:
            # Only the actual NPC conversation roots. Other structural interpretations are not dialogue paths.
            root = path['root_block']
            if root not in [484,1080,1081,1019,485,1082,1083,729,730]:
                continue
            if root not in roots: roots.append(root)
            for rec in path['conditional_records']:
                raw = rec['raw_record']
                kind = 1 if 'score_bounds_raw' in rec else 2 if 'flag_index' in rec else 3 if 'held_item_index' in rec else 4
                rule = [kind, raw[0], raw[1]]
                if rule not in rules: rules.append(rule)
        # Context's old NPC whitelist omitted the pre-56 selector 719.
        for kind, table in enumerate(commands(719)[0]):
            for rec in commands(table):
                target = rec[0] if kind == 3 else rec[2]
                # Solar-zone FlagTimer rcd@0000b1cc raises awake scores <=49 to 50.
                if kind == 3:
                    continue
                if target != block:
                    continue
                if 719 not in roots: roots.append(719)
                rule = [4, rec[0], rec[1]] if kind == 3 else [2 if kind == 0 else 3 if kind == 1 else 1, rec[0], rec[1]]
                # The incidental early statue route repeats 392, not a new deadline.
                if not (block == 392 and kind == 1) and rule not in rules: rules.append(rule)
        score = [r for r in rules if r[0] == 1]
        random = any(r[0] == 4 for r in rules)
        rank = min((r[1] for r in score), default=route.get(block, 150))
        if random:
            rank = min(([16 if r==484 else 76 if r==1080 else 142 for r in roots] if flag>=2900 else [56 if r==485 else 126 if r==1082 else 208 for r in roots]),default=56)
            upper={719:49,484:69,1080:140,1081:199,1019:199,485:119,1082:199,1083:255}
            rules.append([5,0,max(upper[r] for r in roots)])
        text = translations[block].replace('\u3000',' ').strip()
        title = re.split('[。！？…\n]', text)[0].strip('，、 ')
        if len(title)>15: title=title[:14]+'…'
        title=mul_titles[flag-2800] if flag<2900 else elder_titles[flag-2900]
        note=notes.get(block,'')
        if not note and score: note='流程点数'+ '、'.join(f'{r[1]}—{r[2]}' for r in sorted(score))
        if not note and random: note='反复交谈的随机对白；'+('前期' if rank<70 else '中期' if rank<150 else '后期')
        if not note:
            held=next((r for r in rules if r[0]==3),None)
            note='装备对应物品后交谈' if held else '剧情推进后交谈'
        result.append(dict(flag=flag,block=block,person=0 if flag<2900 else 1,rank=rank,title=title,text=text,note=note,rules=rules,roots=roots))
    result.sort(key=lambda r:(r['person'],r['rank'],r['flag']))
    assert len(result)==113 and len({r['flag'] for r in result})==113
    # Mail identity follows Email00..44, not the non-contiguous flag numbers.
    world=json.loads((ROOT/'localization/context/world.json').read_text(encoding='utf-8'))
    mail_notes='村中，启用邮件软件后|离开村中向遗迹前进时|取得手持扫描器，回到村中|地上通往遗迹的入口|地上瀑布一带|取得指引之门的生命宝珠后|指引之门消灭100只蝙蝠后|取得龙骨或无限之钥后|取得圣杯后|取得主武器后，返回对应区域|取得安卡宝石后|指引之门相关机关启动后|巨人陵墓中探索|巨人陵墓中探索|进入太阳神殿|探索太阳神殿|取得赫尔墨斯之靴后|打开守卫封印后|击败第1位守卫后，第2位前|回应长老召回后，回村中|进入空之水源|取得起始之印后|进入灼热洞窟|探索死灭之碑|与妖精女王交谈后，返回无限回廊|击败第2位守卫后，第3位前|进入双连迷宫|发现沉睡之人后|进入巨人墓场|抵达女神之塔上部|取得钩爪后，返回月光圣殿|取得羽毛后，返回地上|双连迷宫取得对应物品后|探索迷失之门或产声之碑|取得对应盾牌后，返回巨人墓场|收到30封邮件后，探索背面区域|研究古代文字的早期阶段|研究古代文字的后续阶段|反复阅读相关石碑后|反复调查相关地点后|流程点数达到140后|流程点数达到180，收到前一封后|流程点数达到200后|击败第4位守卫后，第5位前；升级电脑前|取得龙骨后，探索双连迷宫或迷失之门'.split('|')
    mail_notes[7]='取得龙骨、蛇杖、胡椒或无限之钥后，留在对应区域等收信'
    mail_notes[9]='取得手里剑后，返回对应区域'
    mail_notes[11]='靠近指引之门的单向门'
    mail_notes[17]='取得铜镜后，靠近通往里侧的门'
    mail_notes[19]='收到18号邮件后立即回村找长老，离开帐篷后等收信'
    mail_notes[27]='读取两处里侧圣杯碑后'
    mail_notes[32]='取得时之灯后，留在双连迷宫'
    mail_notes[34]='取得炸弹后，返回巨人墓场'
    mail_notes[36]='学习古代文字前，首次调查未译石碑后等收信'
    mail_notes[37]='学习古代文字前，调查第5处未译石碑后等收信'
    mail_notes[38]='收集10款软件后'
    mail_notes[39]='收集3款NIGORO游戏软件后'
    mail_notes[44]='取得龙骨、蛇杖或胡椒后，向长老展示其他物品前'
    assert len(mail_notes)==45
    mails=[]
    for n,(block,flag) in enumerate(zip([428,429,715,963,365,*range(430,470)],[750,751,841,878,*range(752,793)])):
        paths=[o for o in world['objects'] if any(a['flag_index']==flag and a['value_raw_u8']==1 for a in o['write_operations'])]
        row=canonical[block]
        # Original mail consumers use the first resource LF to separate subject/body.
        segments=row['baseline']['source_segments']
        cut=next(i for i,s in enumerate(segments) if s['kind']=='layout' and '\n' in s.get('text',''))
        title=''.join(r['zh'] for r in row['translation_runs'] if r['source_segment_index']<cut).replace('\u3000',' ').strip()
        text=''.join(r['zh'] for r in row['translation_runs'] if r['source_segment_index']>cut).replace('\u3000',' ').strip()
        assert title and text, f'Mail {n:02}: empty subject/body'
        mails.append(dict(number=n,flag=flag,block=block,title=title,text=text,title_separator_segment=cut,note=mail_notes[n],paths=paths))
    trigger_data = enrich(ROOT, result, mails)
    parsed = json.loads((ROOT/'localization/source/lm1/parsed/data/language/jp/script_code.json').read_text(encoding='utf-8'))
    generate_routes(ROOT, parsed, world)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'dialogues.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def w(s):return 'L'+json.dumps(s,ensure_ascii=True)
    lines=['// Generated by build_catalog.py. Current-save data only.','static const Dialogue DIALOGUES[] = {']
    for r in result:
        rules=(r['rules']+[[0,0,0]]*8)[:8]
        windows=(r['random_windows']+[[0,-1]]*24)[:24]
        assert len(r['random_windows'])<=24
        lines.append('{'+','.join([str(r['flag']),str(r['block']),str(r['person']),str(r['rank']),w(r['title']),w(r['text']),w(r['note']),w(r['short_note']),'{'+','.join('{'+','.join(map(str,x))+'}' for x in rules)+'}', '{'+','.join('{'+','.join(map(str,x))+'}' for x in windows)+'}'])+'},')
    lines.append('};')
    for person,records in enumerate(trigger_data['story']):
        lines.append('static const int STORY_'+str(person)+'[][4]={'+','.join('{'+','.join(map(str,r))+'}' for r in records)+'};')
    (OUT/'mails.json').write_text(json.dumps(mails,ensure_ascii=False,indent=2),encoding='utf-8')
    lines+=['struct Mail { int flag; const wchar_t *title,*text,*note,*shortNote; };','static const Mail MAILS[]={']
    for r in mails:lines.append('{'+','.join([str(r['flag']),w(r['title']),w(r['text']),w(r['note']),w(r['short_note'])])+'},')
    lines.append('};')
    (Path(__file__).parent/'catalog.generated.h').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Built {len(result)} dialogue entries')

if __name__=='__main__':build()

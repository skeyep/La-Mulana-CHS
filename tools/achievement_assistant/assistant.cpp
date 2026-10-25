#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d9.h>
#include <Xinput.h>
#include <algorithm>
#include <string>
#include <vector>
#include <cstdint>

struct Rule { int kind,a,b; };
struct Dialogue { int flag,block,person,rank; const wchar_t *title,*text,*note; Rule rules[8]; };
#include "catalog.generated.h"
#include "skin.generated.h"
static uintptr_t base;
template<class T> T& mem(unsigned va) { return *reinterpret_cast<T*>(base+va-0x400000); }
static unsigned char flag(int n) { return mem<unsigned char>(0x6e1e48+n); }
static short item(int n) { auto p=mem<short*>(0x6e1820); return p?p[n]:0; }
using Task = int (__cdecl*)(void*);
using Init = void (__cdecl*)(void*);
static Init initOriginal;
static void (__cdecl* pollKeyboardOriginal)();
static void* pauseOwner;
static void* pauseHintOwner;
static Init pauseHintDrawOriginal;
static bool opened=false,dirty=true;
static bool waitForRelease=false;
// Native computer opening: 1.15 -> 1.0, -0.03 per update; content follows bezel.
enum { MOTION_IDLE=0, MOTION_OPEN=1, MOTION_READY=2, MOTION_CLOSE=3 };
static int motion=MOTION_IDLE,motionTick=0,shadeAlpha=0;
static float menuScale=1.f;
static DWORD cachedInput=0;
static int tab=0,selected=0,detailScroll=0,person=0;
static DWORD lastPaint=0, previous=0, repeatAt=0;
static HDC dc;
static HBITMAP bitmap;
static HFONT body,smallFont,labelFont;
enum { BODY_SIZE=17, SMALL_SIZE=14, LABEL_SIZE=12, BODY_LEADING=21 };
enum { LIST_PAGE_SIZE=12, ROSTER_COLUMNS=9, ROSTER_COUNT=26 };
static uint32_t* pixels;
static IDirect3DTexture9* texture;
static IDirect3DDevice9* textureDevice;
static std::vector<int> rows;
static const COLORREF ink=RGB(255,255,255),muted=RGB(170,170,170),green=RGB(255,255,255),red=RGB(255,128,128),border=RGB(221,221,221);

static bool missed(const Dialogue& d) {
    // A future forced score reset can reopen an interval. Never use current score alone.
    int floor=flag(123);
    if(flag(898)==0) {
        if(flag(258)<=4)floor=std::min(floor,99);
        if(flag(261)==0)floor=std::min(floor,149);
        if(flag(258)<=7)floor=std::min(floor,199);
    }
    if(flag(124)<2) floor=std::min(floor,12);
    if(flag(124)<13) floor=std::min(floor,150);
    if(flag(258)<8) floor=std::min(floor,200);
    int maxScore=-1;
    for(auto& r:d.rules) if(r.kind==1 || r.kind==5) maxScore=std::max(maxScore,r.b);
    if(maxScore>=0 && floor>maxScore) return true;
    for(auto& r:d.rules) {
        if(r.kind==2 && (r.a==121 || r.a==124 || r.a==844) && flag(r.a)>r.b) return true;
        if(r.kind==2 && r.a>=812 && r.a<=817 && flag(r.a)>r.b) return true;
        if(r.kind==3 && r.a==31 && item(31)==0 && item(81)>0) return true;
    }
    if(d.flag==2806 && flag(193)!=0 && flag(811)==0)return true;
    return false;
}
static const wchar_t* status(const Dialogue& d) { return flag(d.flag)?L"已听":missed(d)?L"已错过":L"未听"; }
static COLORREF statusColor(const Dialogue& d) { return flag(d.flag)?green:missed(d)?red:muted; }
static void selectTab(int t) {
    tab=(t+6)%6; selected=0; detailScroll=0; rows.clear();
    for(int i=0;i<113;i++) if(tab==0 && DIALOGUES[i].person==person) rows.push_back(i);
    dirty=true;
}
static void rect(int x,int y,int w,int h,COLORREF c) { RECT r{x,y,x+w,y+h}; HBRUSH b=CreateSolidBrush(c);FillRect(dc,&r,b);DeleteObject(b); }
static int fontSize(HFONT f) { return f==smallFont?SMALL_SIZE:f==labelFont?LABEL_SIZE:BODY_SIZE; }
#ifdef ASSISTANT_PROFILE
struct ProfileFrame { unsigned phase,totalUs,paintUs,uploadUs; };
struct ProfileData { unsigned count,metricsQueries,extentQueries,reserved; ProfileFrame frames[4096]; };
static ProfileData profile;
static LONGLONG profileNow(){LARGE_INTEGER v;QueryPerformanceCounter(&v);return v.QuadPart;}
static unsigned profileUs(LONGLONG ticks){static LONGLONG frequency=[](){LARGE_INTEGER v;QueryPerformanceFrequency(&v);return v.QuadPart;}();return (unsigned)(ticks*1000000/frequency);}
#endif
static HFONT selectedFont;
static int fontSlot(HFONT f){return f==smallFont?1:f==labelFont?2:0;}
static void selectFont(HFONT f){SelectObject(dc,f);selectedFont=f;}
struct InkMetrics { int top,height,nativeBottom; };
static InkMetrics inkMetrics(HFONT f) {
    static InkMetrics cached[3];static bool valid[3]{};
    selectFont(f);int slot=fontSlot(f);if(valid[slot])return cached[slot];
#ifdef ASSISTANT_PROFILE
    profile.metricsQueries++;
#endif
    TEXTMETRICW tm{};GetTextMetricsW(dc,&tm);
    MAT2 matrix{};matrix.eM11.value=matrix.eM22.value=1;GLYPHMETRICS gm{};
    GetGlyphOutlineW(dc,L'国',GGO_METRICS,&gm,0,nullptr,&matrix);
    int size=fontSize(f),bottom=0;
    for(int y=0;y<size;y++)for(int x=0;x<21;x++)if(NATIVE_ALPHA[L'0'*441+(y*21/size)*21+x])bottom=y;
    cached[slot]={tm.tmAscent-gm.gmptGlyphOrigin.y,(int)gm.gmBlackBoxY,bottom};valid[slot]=true;return cached[slot];
}
static int middleY(int y,int height,HFONT f) { return y+(height-inkMetrics(f).height)/2; }
static unsigned short glyphWidths[3][65536]{};
static bool batchable(wchar_t c){return (c>=0x3400 && c<=0x9fff) || wcschr(L"，。！？、：；（）《》【】「」『』～",c)!=nullptr;}
static void primeWidths(const wchar_t* text,size_t count,HFONT f) {
    auto& widths=glyphWidths[fontSlot(selectedFont?selectedFont:f)];std::wstring missing;
    for(size_t i=0;i<count;i++){wchar_t c=text[i];if(batchable(c) && !widths[(unsigned short)c] && missing.find(c)==std::wstring::npos)missing+=c;}
    if(missing.empty())return;
    std::vector<int> dx(missing.size());SIZE size{};
#ifdef ASSISTANT_PROFILE
    profile.extentQueries++;
#endif
    if(GetTextExtentExPointW(dc,missing.data(),(int)missing.size(),0x7fffffff,nullptr,dx.data(),&size)){
        int previous=0;for(size_t i=0;i<missing.size();i++){widths[(unsigned short)missing[i]]=(unsigned short)(dx[i]-previous+1);previous=dx[i];}
    }
}
static float advance(wchar_t c,HFONT f) {
    int size=fontSize(f);if(c==L' ')return size*.5f;
    if(c<128 && NATIVE_WIDTHS[c])return NATIVE_WIDTHS[c]*size/21.f;
    // Preserve the selected GDI font, including existing measure() callers.
    auto& cached=glyphWidths[fontSlot(selectedFont?selectedFont:f)][(unsigned short)c];
    if(cached)return (float)(cached-1);
#ifdef ASSISTANT_PROFILE
    profile.extentQueries++;
#endif
    SIZE extent;GetTextExtentPoint32W(dc,&c,1,&extent);cached=(unsigned short)(extent.cx+1);return (float)extent.cx;
}
static float measure(const std::wstring& s,HFONT f) {primeWidths(s.data(),s.size(),f);float w=0;for(wchar_t c:s)w+=advance(c,f);return w;}
static void nativeGlyph(int x,int y,wchar_t c,int size,COLORREF color) {
    GdiFlush();int width=(NATIVE_WIDTHS[c]*size+20)/21;
    for(int yy=0;yy<size;yy++)for(int xx=0;xx<width;xx++) {
        if(x+xx<0||x+xx>=640||y+yy<0||y+yy>=480)continue;
        int a=NATIVE_ALPHA[c*441+(yy*21/size)*21+xx*21/size];if(!a)continue;
        auto& p=pixels[(y+yy)*640+x+xx];
        int r=(GetRValue(color)*a+((p>>16)&255)*(255-a))/255;
        int g=(GetGValue(color)*a+((p>>8)&255)*(255-a))/255,b=(GetBValue(color)*a+(p&255)*(255-a))/255;
        p=(r<<16)|(g<<8)|b;
    }
}
static void text(int x,int y,int w,const std::wstring& s,COLORREF c=ink,HFONT font=nullptr) {
    HFONT f=font?font:body;selectFont(f);SetTextColor(dc,c);SetBkMode(dc,TRANSPARENT);
    std::wstring shown=s;
    if(measure(shown,f)>w){while(!shown.empty()&&measure(shown+L"…",f)>w)shown.pop_back();shown+=L"…";}
    float dx=(float)x;
    auto metrics=inkMetrics(f);
    for(size_t i=0;i<shown.size();){
        wchar_t ch=shown[i];
        if(ch<128&&NATIVE_WIDTHS[ch]){nativeGlyph((int)(dx+.5f),y+metrics.height-1-metrics.nativeBottom,ch,fontSize(f),c);dx+=advance(ch,f);i++;}
        else if(batchable(ch)){
            size_t end=i+1;while(end<shown.size() && batchable(shown[end]))end++;
            TextOutW(dc,(int)(dx+.5f),y-metrics.top,shown.data()+i,(int)(end-i));
            for(;i<end;i++)dx+=advance(shown[i],f);
        }else {if(ch!=L' ')TextOutW(dc,(int)(dx+.5f),y-metrics.top,&ch,1);dx+=advance(ch,f);i++;}
    }
}
static void section(int x,int y,int w,int h,const wchar_t* label,int labelWidth=112) {
    rect(x,y,labelWidth,14,RGB(28,33,48));
    rect(x,y,labelWidth,1,border);rect(x,y,1,h,border);rect(x+labelWidth,y,1,15,border);
    rect(x+labelWidth,y+14,w-labelWidth,1,border);rect(x+w-1,y+14,1,h-14,border);rect(x,y+h-1,w,1,border);
    text(x+4,y+1,labelWidth-7,label,ink,labelFont);
}
static void cursor(int x,int y,int w,int h) {
    GdiFlush();
    for(int c=0;c<4;c++)for(int yy=0;yy<24;yy++)for(int xx=0;xx<24;xx++) {
        auto p=MENU_CORNER[yy*24+xx];int a=p>>24;if(!a)continue;
        int dx=x+((c&1)?w-1-xx:xx),dy=y+((c&2)?h-1-yy:yy);
        if(dx<0||dx>=640||dy<0||dy>=480)continue;
        uint32_t& q=pixels[dy*640+dx];int r=(((p>>16)&255)*a+((q>>16)&255)*(255-a))/255;
        int g=(((p>>8)&255)*a+((q>>8)&255)*(255-a))/255,b=((p&255)*a+(q&255)*(255-a))/255;
        q=(r<<16)|(g<<8)|b;
    }
}
static std::vector<std::wstring> wrap(const wchar_t* s,int width) {
    selectFont(body);primeWidths(s,wcslen(s),body);std::vector<std::wstring> result;std::wstring line;float lineWidth=0;
    for(const wchar_t* p=s;*p;p++) {
        if(*p==L'\n') {result.push_back(line);line.clear();lineWidth=0;continue;}
        float nextWidth=advance(*p,body);
        if(lineWidth+nextWidth>width && !line.empty()){
            std::wstring carry;
            if(line.size()>1 && (wcschr(L"，。！？、：；）》】」』…",*p) || wcschr(L"（《【「『",line.back()))) {
                carry+=line.back();line.pop_back();
            }
            result.push_back(line);line=carry;lineWidth=measure(line,body);
        }
        line+=*p;lineWidth+=nextWidth;
    }
    if(!line.empty())result.push_back(line);return result;
}
static void excerpt(const wchar_t* content,int x,int y,int width,int bottom) {
    auto lines=wrap(content,width);int count=std::max(0,(bottom-y)/BODY_LEADING);
    for(int i=0;i<std::min(count,(int)lines.size());i++) {
        auto line=lines[i];
        if(i==count-1 && (int)lines.size()>count){selectFont(body);while(!line.empty()&&measure(line+L"…",body)>width)line.pop_back();line+=L"…";}
        text(x,y+i*BODY_LEADING,width,line);
    }
}
static HFONT makeFont(int size) {
    return CreateFontW(-size,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,ANTIALIASED_QUALITY,DEFAULT_PITCH,L"霞鹜臻楷 GB");
}
static void initCanvas() {
    if(dc)return;
    wchar_t gamePath[MAX_PATH];GetModuleFileNameW(nullptr,gamePath,MAX_PATH);
    std::wstring fontPath(gamePath);fontPath.resize(fontPath.find_last_of(L"\\/")+1);
    fontPath+=L"data\\language\\chs\\assistant-font.ttf";
    AddFontResourceExW(fontPath.c_str(),FR_PRIVATE,nullptr);
    dc=CreateCompatibleDC(nullptr);BITMAPINFO info{};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=640;info.bmiHeader.biHeight=-480;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
    bitmap=CreateDIBSection(dc,&info,DIB_RGB_COLORS,(void**)&pixels,nullptr,0);SelectObject(dc,bitmap);
    body=makeFont(BODY_SIZE);smallFont=makeFont(SMALL_SIZE);
    labelFont=makeFont(LABEL_SIZE);
}
static void paintDialogue() {
    int total=0;for(int i:rows)if(flag(DIALOGUES[i].flag))total++;
    section(20,60,316,388,L"",144);section(342,60,278,388,L"对话正文");
    const wchar_t* people[]={L"穆尔",L"长老"};
    for(int n=0;n<2;n++) {
        int x=20+n*72;
        rect(x,60,72,15,RGB(28,33,48));
        rect(x,60,72,1,border);rect(x,60,1,15,border);rect(x+71,60,1,15,border);
        text(x+(72-(int)measure(people[n],labelFont))/2,middleY(60,14,labelFont),68,people[n],n==person?ink:RGB(128,128,128),labelFont);
    }
    const std::wstring personHint=L"物品键：换人物";
    text(328-(int)measure(personHint,labelFont),middleY(60,15,labelFont),164,personHint,ink,labelFont);
    text(28,81,300,L"已听 "+std::to_wstring(total)+L" / "+std::to_wstring(rows.size())+L"     当前流程点数 "+std::to_wstring(flag(123)),ink,smallFont);
    const int start=selected/LIST_PAGE_SIZE*LIST_PAGE_SIZE;
    for(int n=start;n<std::min(start+LIST_PAGE_SIZE,(int)rows.size());n++) {
        auto& d=DIALOGUES[rows[n]];int y=106+(n-start)*27;
        if(n==selected)cursor(53,y-2,213,26);
        text(29,middleY(y-2,26,smallFont),29,std::to_wstring(n+1),muted,smallFont);
        text(62,middleY(y-2,26,body),202,flag(d.flag)?d.title:L"？？？",n==selected?red:ink);
        text(276,middleY(y-2,26,smallFont),57,status(d),statusColor(d),smallFont);
    }
    text(29,429,300,L"流程顺序  "+std::to_wstring(selected+1)+L" / "+std::to_wstring(rows.size()),muted,smallFont);
    if(rows.empty())return;
    auto& d=DIALOGUES[rows[selected]];
    text(352,82,258,flag(d.flag)?L"已听":missed(d)?L"已错过":L"未听",statusColor(d));
    auto timing=wrap(d.note,256);int y=110;
    for(int i=0;i<std::min(3,(int)timing.size());i++,y+=BODY_LEADING)text(352,y,256,timing[i],muted);
    rect(352,y+3,257,1,RGB(100,100,100));y+=16;
    if(!flag(d.flag)){detailScroll=0;text(352,y,256,L"？？？",muted);return;}
    excerpt(d.text,352,y,256,440);
}
struct TimedTarget { unsigned limit;int awardedFlag;const wchar_t* label; };
static const TimedTarget TIMED_TARGETS[]={{36000000,3023,L"10小时内"},{72000000,3022,L"20小时内"},{144000000,3021,L"40小时内"}};
static std::wstring duration(unsigned milliseconds) {
    unsigned seconds=milliseconds/1000;
    auto pad=[](unsigned n){return (n<10?std::wstring(L"0"):std::wstring())+std::to_wstring(n);};
    return pad(seconds/3600)+L":"+pad(seconds/60%60)+L":"+pad(seconds%60);
}
static const wchar_t* timedStatus(const TimedTarget& target,unsigned elapsed) {
    if(flag(target.awardedFlag))return L"已达成";
    if(flag(3020))return L"未达成";
    return elapsed<=target.limit?L"尚未超时":L"已超时";
}
static void paintChallenges() {
    int won=0;for(int n=3011;n<=3019;n++)if(flag(n))won++;
    section(20,60,600,151,L"无副武器击败守卫",200);
    text(34,96,200,L"不限难度",ink);text(260,96,32,L"：");text(304,96,280,std::to_wstring(flag(3056))+L" / 9",red);
    text(34,143,200,L"困难模式",ink);text(260,143,32,L"：");text(304,143,280,std::to_wstring(flag(3057))+L" / 9",red);
    if(won>flag(3056))text(407,middleY(96,inkMetrics(body).height,smallFont),205,L"已错过",red,smallFont);
    if(won>flag(3057))text(407,middleY(143,inkMetrics(body).height,smallFont),205,L"已错过",red,smallFont);
    section(20,218,600,94,L"最近战斗记录",200);
    text(34,253,242,L"副武器使用",ink);text(260,253,32,L"：");
    text(304,253,294,mem<int>(0xdc3874)?L"已记录":L"未记录",mem<int>(0xdc3874)?red:ink);
    section(20,320,600,128,L"限时通关",136);
    unsigned elapsed=mem<unsigned>(0x6e1214);
    text(30,343,132,L"当前用时",ink,smallFont);text(178,343,220,duration(elapsed),ink,smallFont);
    for(int i=0;i<3;i++){
        const auto& target=TIMED_TARGETS[i];int y=370+i*24;
        bool done=flag(target.awardedFlag)!=0,finished=flag(3020)!=0,within=elapsed<=target.limit;
        text(30,y,132,target.label,ink,smallFont);
        std::wstring remaining=(done||finished||!within)?L"—":L"剩余 "+duration(target.limit-elapsed);
        text(178,y,272,remaining,muted,smallFont);
        text(474,y,128,timedStatus(target,elapsed),done?ink:finished||!within?red:ink,smallFont);
    }
}

static bool mailMissed(const Mail& m) {
    // Verified closed windows; unresolved route-specific predicates remain unclassified.
    if(m.flag==766 && flag(258)>1)return true;
    if(m.flag==773 && flag(258)>2)return true;
    if(m.flag==791 && (flag(258)>4 || flag(541)!=0))return true;
    if(m.flag==767 && (flag(124)>4 || flag(773)!=0 || flag(791)==1))return true;
    if(m.flag==784 && (flag(746)!=0 || flag(747)>1))return true;
    if(m.flag==785 && (flag(746)!=0 || flag(747)>5))return true;
    if(m.flag==792 && flag(743)!=0)return true;
    return flag(898)!=0 && m.flag!=784 && m.flag!=785 && m.flag!=792;
}
static void paintMail() {
    section(20,60,316,388,L"邮件列表");
    std::wstring heading=L"邮件 "+(selected<10?std::wstring(L"0"):std::wstring())+std::to_wstring(selected);
    section(342,60,278,388,heading.c_str());
    int total=0;for(auto& m:MAILS)if(flag(m.flag))total++;
    text(28,81,300,L"已收 "+std::to_wstring(total)+L" / 45",ink,smallFont);
    int start=selected/LIST_PAGE_SIZE*LIST_PAGE_SIZE;
    for(int n=start;n<std::min(start+LIST_PAGE_SIZE,45);n++) {
        const auto& m=MAILS[n];bool got=flag(m.flag)!=0;int y=106+(n-start)*27;
        if(n==selected)cursor(53,y-2,213,26);
        text(29,middleY(y-2,26,smallFont),29,(n<10?L"0":L"")+std::to_wstring(n),muted,smallFont);
        text(62,middleY(y-2,26,body),202,got?m.title:L"？？？",n==selected?red:ink);
        text(276,middleY(y-2,26,smallFont),57,got?L"已收":mailMissed(m)?L"已错过":L"未收",got?ink:mailMissed(m)?red:muted,smallFont);
    }
    text(29,429,300,L"邮件顺序  "+std::to_wstring(selected+1)+L" / 45",muted,smallFont);
    const auto& m=MAILS[selected];bool got=flag(m.flag)!=0;
    text(352,82,258,got?L"已收":mailMissed(m)?L"已错过":L"未收",got?ink:mailMissed(m)?red:muted);
    int y=110;for(auto& line:wrap(m.note,256)){text(352,y,256,line,muted);y+=BODY_LEADING;}
    rect(352,y+3,257,1,RGB(100,100,100));y+=16;
    if(!got){text(352,y,256,L"？？？",muted);return;}
    excerpt(m.text,352,y,256,440);
}
static void paintCurry() {
    const wchar_t* labels[]={L"平常休息",L"泡温泉",L"在水中游泳",L"在熔岩中游泳",L"守卫战／圣母前段",L"圣母战后段",L"逃脱倒计时",L"受伤硬直",L"高处落地硬直",L"在冰上滑行"};
    int total=0;for(int n=0;n<10;n++)if(flag(3180+n))total++;
    section(20,60,600,388,L"咖喱记录",136);
    text(30,82,576,L"已完成 "+std::to_wstring(total)+L" / 10",ink,smallFont);
    for(int n=0;n<10;n++){
        int x=30+(n/5)*300,y=119+(n%5)*54;bool got=flag(3180+n)!=0;
        text(x,middleY(y,22,body),212,labels[n],got?ink:muted);text(x+218,middleY(y,22,smallFont),62,got?L"已完成":L"未完成",got?ink:muted,smallFont);
    }
    text(30,416,576,L"在对应场景暂停，等待勒美沙开始休息。",muted,smallFont);
}
static void paintCollection() {
    section(20,60,600,388,L"收集总览",136);
    int maps=0,soft=0,scan=0;
    for(int n=209;n<=225;n++)if(flag(n)==2)maps++;
    for(int n=85;n<=104;n++)if(item(n))soft++;
    for(int n=3200;n<=3330;n++)if(flag(n))scan++;
    const wchar_t* labels[]={L"地图",L"软件",L"生命宝珠",L"扫描点",L"妖精点",L"妖精锁",L"金币宝箱"};
    const int values[]={maps,soft,flag(852),scan,flag(900),flag(902),flag(119)},totals[]={17,20,10,131,9,4,28};
    for(int n=0;n<7;n++) {
        int y=92+n*49;bool done=values[n]==totals[n];
        text(34,middleY(y,23,body),244,labels[n]);text(300,middleY(y,23,body),154,std::to_wstring(values[n])+L" / "+std::to_wstring(totals[n]),done?ink:muted);
        text(496,middleY(y,23,smallFont),100,done?L"已集齐":L"未集齐",done?ink:muted,smallFont);
    }
}

static void paintRoster();
static void paintTab(int x,int width,bool active) {
    GdiFlush();const unsigned* strip=active?TAB_ACTIVE:TAB_IDLE;
    for(int y=0;y<22;y++)for(int dx=0;dx<width;dx++){
        int sx=dx<4?dx:dx>=width-4?width-1-dx:4;
        pixels[(32+y)*640+x+dx]=strip[y*5+sx]&0xffffff;
    }
}
static void paint() {
    initCanvas();GdiFlush();memset(pixels,0,640*480*4);
    if(!opened) {
        rect(202,42,236,42,RGB(17,17,17));
        section(202,32,236,52,L"汉化版独占功能",116);cursor(213,50,214,27);
        text(223,middleY(50,27,body),204,L"跳跃键：冒险记录",ink);return;
    }
    memcpy(pixels,MENU_SKIN,640*480*4);
    // The native opening shows only the bezel; defer hidden text/layout work.
    if(motion!=MOTION_READY)return;
    const wchar_t* tabs[]={L"对话",L"邮件",L"咖喱",L"通关挑战",L"收集",L"结局同行"};
    const int tx[]={21,97,173,249,365,441},tw[]={75,75,75,115,75,177};
    selectFont(body);
    for(int n=0;n<6;n++){
        paintTab(tx[n],tw[n],tab==n);
        text(tx[n]+(tw[n]-(int)measure(tabs[n],body))/2,32+(22-inkMetrics(body).height)/2,tw[n],tabs[n],ink,body);
    }
    if(tab==0)paintDialogue();else if(tab==1)paintMail();else if(tab==2)paintCurry();else if(tab==3)paintChallenges();else if(tab==4)paintCollection();else paintRoster();
}
struct Vertex {float x,y,z,rhw;DWORD color;float u,v;};
static void draw() {
    if(!pauseOwner)return;auto dev=mem<IDirect3DDevice9*>(0xdc3858);if(!dev)return;
    if(!opened && *reinterpret_cast<int*>((BYTE*)pauseOwner+0x1c)!=0)return;
    if(textureDevice!=dev){if(texture)texture->Release();texture=nullptr;textureDevice=dev;dirty=true;}
    if(!texture && FAILED(dev->CreateTexture(640,480,1,0,D3DFMT_A8R8G8B8,D3DPOOL_MANAGED,&texture,nullptr)))return;
#ifdef ASSISTANT_PROFILE
    const LONGLONG profileStart=profileNow();unsigned paintUs=0,uploadUs=0;
#endif
    if(dirty || (opened && motion==MOTION_READY && GetTickCount()-lastPaint>250)) {
#ifdef ASSISTANT_PROFILE
        LONGLONG paintStart=profileNow();
#endif
        paint();GdiFlush();D3DLOCKED_RECT lock;
#ifdef ASSISTANT_PROFILE
        paintUs=profileUs(profileNow()-paintStart);LONGLONG uploadStart=profileNow();
#endif
        if(SUCCEEDED(texture->LockRect(0,&lock,nullptr,0))) {
            for(int y=0;y<480;y++)for(int x=0;x<640;x++){
                int i=y*640+x;DWORD p=pixels[i]&0xffffff;
                DWORD alpha=opened?((p==(MENU_SKIN[i]&0xffffff))?(MENU_SKIN[i]>>24):255):(p?255:0);
                if(opened && motion!=MOTION_READY && x>=18 && x<622 && y>=30 && y<450)alpha=0;
                ((DWORD*)((BYTE*)lock.pBits+y*lock.Pitch))[x]=p|(alpha<<24);
            }
            texture->UnlockRect(0);
        }
#ifdef ASSISTANT_PROFILE
        uploadUs=profileUs(profileNow()-uploadStart);
#endif
        dirty=false;lastPaint=GetTickCount();
    }
    IDirect3DStateBlock9* saved=nullptr;if(FAILED(dev->CreateStateBlock(D3DSBT_ALL,&saved)))return;saved->Capture();
    D3DVIEWPORT9 view;dev->GetViewport(&view);float sx=view.Width/640.f,sy=view.Height/480.f;
    float scale=opened?menuScale:1.f;
    float x0=320*(1-scale)*sx-.5f,y0=240*(1-scale)*sy-.5f;
    float x1=320*(1+scale)*sx-.5f,y1=240*(1+scale)*sy-.5f;
    Vertex verts[]={{x0,y0,0,1,0xffffffff,0,0},{x1,y0,0,1,0xffffffff,1,0},{x0,y1,0,1,0xffffffff,0,1},{x1,y1,0,1,0xffffffff,1,1}};
    dev->SetVertexShader(nullptr);dev->SetPixelShader(nullptr);dev->SetFVF(D3DFVF_XYZRHW|D3DFVF_DIFFUSE|D3DFVF_TEX1);
    dev->SetRenderState(D3DRS_ZENABLE,FALSE);dev->SetRenderState(D3DRS_ALPHABLENDENABLE,TRUE);dev->SetRenderState(D3DRS_SRCBLEND,D3DBLEND_SRCALPHA);dev->SetRenderState(D3DRS_DESTBLEND,D3DBLEND_INVSRCALPHA);
    dev->SetRenderState(D3DRS_ALPHATESTENABLE,FALSE);dev->SetRenderState(D3DRS_CULLMODE,D3DCULL_NONE);dev->SetRenderState(D3DRS_SCISSORTESTENABLE,FALSE);
    if(opened && shadeAlpha){
        DWORD shade=(DWORD)shadeAlpha<<24;
        Vertex backdrop[]={{-.5f,-.5f,0,1,shade,0,0},{640*sx-.5f,-.5f,0,1,shade,1,0},{-.5f,480*sy-.5f,0,1,shade,0,1},{640*sx-.5f,480*sy-.5f,0,1,shade,1,1}};
        dev->SetTexture(0,nullptr);dev->SetTextureStageState(0,D3DTSS_COLOROP,D3DTOP_SELECTARG1);dev->SetTextureStageState(0,D3DTSS_COLORARG1,D3DTA_DIFFUSE);
        dev->SetTextureStageState(0,D3DTSS_ALPHAOP,D3DTOP_SELECTARG1);dev->SetTextureStageState(0,D3DTSS_ALPHAARG1,D3DTA_DIFFUSE);dev->SetTextureStageState(1,D3DTSS_COLOROP,D3DTOP_DISABLE);
        dev->DrawPrimitiveUP(D3DPT_TRIANGLESTRIP,2,backdrop,sizeof(Vertex));
    }
    dev->SetTexture(0,texture);dev->SetTextureStageState(0,D3DTSS_COLOROP,D3DTOP_SELECTARG1);dev->SetTextureStageState(0,D3DTSS_COLORARG1,D3DTA_TEXTURE);dev->SetTextureStageState(0,D3DTSS_ALPHAOP,D3DTOP_SELECTARG1);dev->SetTextureStageState(0,D3DTSS_ALPHAARG1,D3DTA_TEXTURE);dev->SetTextureStageState(1,D3DTSS_COLOROP,D3DTOP_DISABLE);
    dev->SetSamplerState(0,D3DSAMP_MINFILTER,D3DTEXF_POINT);dev->SetSamplerState(0,D3DSAMP_MAGFILTER,D3DTEXF_POINT);
    dev->DrawPrimitiveUP(D3DPT_TRIANGLESTRIP,2,verts,sizeof(Vertex));saved->Apply();saved->Release();
#ifdef ASSISTANT_PROFILE
    if(profile.count<4096)profile.frames[profile.count++]={opened?(unsigned)motion:0,profileUs(profileNow()-profileStart),paintUs,uploadUs};
#endif
}
enum {OPEN=1,CLOSE=2,UP=4,DOWN=8,LEFT=16,RIGHT=32,PREV_TAB=64,NEXT_TAB=128,PERSON=256};
// The original action query takes the action in EDI and held/pressed mode in EAX.
static bool mappedHeld(int action) {
    uintptr_t query=base+0x832a0;int result;
    __asm {
        push edi
        mov edi,action
        xor eax,eax
        call query
        mov result,eax
        pop edi
    }
    return result!=0;
}
// Same configurable menu actions as the native settings page (30=settings, 5=back).
static bool menuHeld(int action) {
    return reinterpret_cast<int (__cdecl*)(int,int)>(base+0xb9ae0)(0,action)!=0;
}
static DWORD input() {
    DWORD v=0;
    if(mappedHeld(4))v|=OPEN;
    if(menuHeld(5) || menuHeld(22) || menuHeld(30))v|=CLOSE;
    if(menuHeld(3))v|=PERSON;
    if(mappedHeld(0))v|=UP;if(mappedHeld(1))v|=DOWN;
    if(mappedHeld(2))v|=LEFT;if(mappedHeld(3))v|=RIGHT;
    if(menuHeld(16))v|=PREV_TAB;if(menuHeld(17))v|=NEXT_TAB;
    return v;
}
// Read controls before masking the game's input buffers. Other tasks must not
// react to a modal page's keys, including the key that closes the page.
static void __cdecl pollKeyboard() {
    pollKeyboardOriginal();
    if(!pauseOwner)return;
    cachedInput=input();
    if(waitForRelease && !(cachedInput&(OPEN|CLOSE)))waitForRelease=false;
    if(opened || waitForRelease || ((cachedInput&OPEN) && *reinterpret_cast<int*>((BYTE*)pauseOwner+0x1c)==0)) {
        memset((void*)(base+0x2dffe0),0,0xc00);
        reinterpret_cast<void (__cdecl*)()>(base+0x271a60)();
    }
}
static void __cdecl pauseHintDraw(void* p) { if(!opened && pauseHintDrawOriginal)pauseHintDrawOriginal(p); }
static void bindPauseHint(void* p) {
    void* hint=*reinterpret_cast<void**>((BYTE*)p+0xa8);
    if(hint!=pauseHintOwner) {
        pauseHintOwner=hint;pauseHintDrawOriginal=nullptr;
        if(hint) {
            pauseHintDrawOriginal=*reinterpret_cast<Init*>((BYTE*)hint+0x10);
            *reinterpret_cast<Init*>((BYTE*)hint+0x10)=pauseHintDraw;
        }
    }
}
static void moveRoster(DWORD pressed) {
    int row=selected/ROSTER_COLUMNS,column=selected%ROSTER_COLUMNS;
    if(pressed&LEFT)column=std::max(0,column-1);
    if(pressed&RIGHT)column=std::min(std::min(ROSTER_COLUMNS-1,ROSTER_COUNT-1-row*ROSTER_COLUMNS),column+1);
    if(pressed&UP)row=std::max(0,row-1);
    if(pressed&DOWN)row=std::min((ROSTER_COUNT-1)/ROSTER_COLUMNS,row+1);
    selected=std::min(ROSTER_COUNT-1,row*ROSTER_COLUMNS+column);dirty=true;
}
static int __cdecl pauseUpdate(void* p) {
    bindPauseHint(p);
    DWORD now=cachedInput,pressed=now&~previous;DWORD tick=GetTickCount();
    if(now!=previous)repeatAt=tick+500;else if(now && tick>=repeatAt){pressed|=now&(UP|DOWN|LEFT|RIGHT);repeatAt=tick+130;}previous=now;
    int state=*reinterpret_cast<int*>((BYTE*)p+0x1c);
    if(!opened && state==0 && !waitForRelease && (pressed&OPEN)){
        opened=true;motion=MOTION_OPEN;motionTick=0;menuScale=1.15f;shadeAlpha=0;
        person=0;dirty=true;selectTab(0);return 1;
    }
    if(opened){
        shadeAlpha=motion==MOTION_CLOSE?std::max(0,shadeAlpha-16):std::min(160,shadeAlpha+16);
        if(motion==MOTION_OPEN){
            if(++motionTick>1)menuScale=std::max(1.f,menuScale-.03f);
            if(motionTick>=7){menuScale=1.f;motion=MOTION_READY;dirty=true;}
            return 1;
        }
        if(motion==MOTION_CLOSE){
            menuScale+=.03f;
            if(++motionTick>=6){opened=false;motion=MOTION_IDLE;menuScale=1.f;waitForRelease=true;dirty=true;}
            return 1;
        }
        if(pressed&CLOSE){motion=MOTION_CLOSE;motionTick=0;waitForRelease=true;dirty=true;return 1;}
        if(pressed&PREV_TAB)selectTab(tab-1);if(pressed&NEXT_TAB)selectTab(tab+1);
        if(tab==0 && (pressed&PERSON)){person=1-person;selectTab(tab);}
        if(tab==5 && (pressed&(UP|DOWN|LEFT|RIGHT)))moveRoster(pressed);
        else {
            int n=tab==0?(int)rows.size():tab==1?45:0;
            int delta=(pressed&DOWN?1:0)-(pressed&UP?1:0)+(pressed&RIGHT?LIST_PAGE_SIZE:0)-(pressed&LEFT?LIST_PAGE_SIZE:0);
            if(n && delta){selected=std::clamp(selected+delta,0,n-1);detailScroll=0;dirty=true;}
        }
        return 1;
    }
    return reinterpret_cast<Task>(base+0x188320)(p);
}
static int __cdecl pauseCleanup(void* p) {
    if(pauseHintOwner && *reinterpret_cast<void**>((BYTE*)p+0xa8)==pauseHintOwner)
        *reinterpret_cast<Init*>((BYTE*)pauseHintOwner+0x10)=pauseHintDrawOriginal;
    pauseHintOwner=nullptr;pauseHintDrawOriginal=nullptr;pauseOwner=nullptr;opened=false;motion=MOTION_IDLE;menuScale=1.f;waitForRelease=false;dirty=true;
    return reinterpret_cast<Task>(base+0x1882b0)(p);
}
static void __cdecl pauseDraw(void* p) { if(!opened)reinterpret_cast<Init>(base+0x188c50)(p);draw(); }
static void __cdecl pauseInit(void* p) {
    initOriginal(p);if(mem<BYTE>(0x6e0e5f))return;
    pauseOwner=p;opened=false;motion=MOTION_IDLE;menuScale=1.f;waitForRelease=false;dirty=true;cachedInput=previous=input();selectTab(tab);
    *reinterpret_cast<Task*>((BYTE*)p+4)=pauseUpdate;*reinterpret_cast<Task*>((BYTE*)p+0x14)=pauseCleanup;
    *reinterpret_cast<Init*>((BYTE*)p+0x10)=pauseDraw;
}
static void* hook(unsigned va,void* target,int length) {
    BYTE* address=(BYTE*)(base+va-0x400000);BYTE* tramp=(BYTE*)VirtualAlloc(nullptr,length+5,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE);
    if(!tramp)return nullptr;memcpy(tramp,address,length);tramp[length]=0xe9;*(int*)(tramp+length+1)=(int)(address+length-(tramp+length+5));
    DWORD old;VirtualProtect(address,length,PAGE_EXECUTE_READWRITE,&old);address[0]=0xe9;*(int*)(address+1)=(int)((BYTE*)target-address-5);for(int i=5;i<length;i++)address[i]=0x90;VirtualProtect(address,length,old,&old);FlushInstructionCache(GetCurrentProcess(),address,length);return tramp;
}
// Roster implementation is kept separate from the read-only dialogue rules.
#include "roster.h"
extern "C" __declspec(dllexport) void* __cdecl AssistantState() {
    static uintptr_t state[8];state[0]=opened;state[1]=tab;state[2]=selected;state[3]=(uintptr_t)pauseOwner;state[4]=detailScroll;state[5]=person;state[6]=motion;state[7]=motionTick;return state;
}
extern "C" __declspec(dllexport) void* __cdecl AssistantSnapshot() {
    static int values[184];for(int i=0;i<113;i++)values[i]=flag(DIALOGUES[i].flag)?1:missed(DIALOGUES[i])?2:0;
    for(int i=0;i<26;i++)values[113+i]=rosterReady(companions[i].rule);
    for(int i=0;i<45;i++)values[139+i]=flag(MAILS[i].flag)?1:mailMissed(MAILS[i])?2:0;
    return values;
}
#ifdef ASSISTANT_PROFILE
extern "C" __declspec(dllexport) void* __cdecl AssistantProfile(){return &profile;}
extern "C" __declspec(dllexport) void __cdecl AssistantProfileReset(){memset(&profile,0,sizeof(profile));}
extern "C" __declspec(dllexport) void* __cdecl AssistantProfileCanvas(){GdiFlush();return pixels;}
extern "C" __declspec(dllexport) void __cdecl AssistantProfileSelect(int t,int p,int row){person=p;selectTab(t);selected=row;dirty=true;}
#endif
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID) {
    if(reason!=DLL_PROCESS_ATTACH)return TRUE;DisableThreadLibraryCalls(instance);base=(uintptr_t)GetModuleHandleW(nullptr);
    const BYTE expected[]={0x55,0x8b,0xec,0x83,0xec,0x08};
    if(memcmp((void*)(base+0x187b60),expected,6)!=0)return FALSE;
    const BYTE keyboardExpected[]={0x55,0x8b,0xec,0x83,0xec,0x0c};
    if(memcmp((void*)(base+0x55860),keyboardExpected,6)!=0)return FALSE;
    pollKeyboardOriginal=(void (__cdecl*)())hook(0x455860,(void*)pollKeyboard,6);
    if(!pollKeyboardOriginal)return FALSE;
    initOriginal=(Init)hook(0x587b60,(void*)pauseInit,6);
    return initOriginal!=nullptr;
}

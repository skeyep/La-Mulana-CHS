// Ending case 10 in 0x466530, plus Lemeza/Mulbruk and final Shawn entry.
#include "portraits.generated.h"
struct Companion {const wchar_t* name;const wchar_t* condition;int rule;};
static const Companion companions[]={
 {L"勒美沙",L"",0},{L"穆尔",L"",0},
 {L"长老",L"",0},{L"村中妇人",L"",0},
 {L"村中孩子",L"",0},{L"西德罗",L"",0},
 {L"莫德罗",L"",0},{L"涅布尔",L"收集全部17张地图",1},
 {L"治愈妖精",L"向妖精女王出示伊西斯吊坠",2},{L"妖精女王",L"填满全部道具栏",3},
 {L"吉尔特利尤",L"取得《拉穆拉纳》软件",4},{L"武器妖精",L"在全部9处妖精点各召出一次妖精",5},
 {L"阿尔赛达纳",L"收集全部10颗生命宝珠",6},{L"骷髅",L"收集全部20款软件",7},
 {L"祭品少女",L"收到全部45封邮件",8},{L"沙玛兰特",L"40小时内通关",9},
 {L"道具妖精",L"打开全部金币宝箱；包含逃脱时的宝箱",10},{L"福沃斯",L"取得音乐播放软件",11},
 {L"阿尔戈斯",L"20小时内通关",12},{L"钥匙妖精",L"打开4处妖精锁；不含地狱圣殿",13},
 {L"鲁萨莉",L"10小时内通关",14},{L"杜拉库艾茨",L"通关地狱圣殿并取得泳装",15},
 {L"鱼人",L"在鱼人商店购买海螺或公会软件",16},{L"Naramura",L"拜访全部3位开发者",17},
 {L"圣母",L"在困难模式击败全部守卫与圣母",18},{L"肖恩",L"",0}
};
static bool rosterReady(int r) {
 switch(r) {
 case 0:return true;
 case 1:for(int n=209;n<=225;n++)if(flag(n)!=2)return false;return true;
 case 2:return flag(280)==1;
 case 3:{
    if(!(item(0)||item(1)||item(2))||!item(3)||!(item(4)||item(7))||!item(5)||!item(6))return false;
    for(int n=8;n<=15;n++)if(!item(n))return false;
    if(!(item(16)||item(75)||item(17)||item(18)))return false;
    const int required[]={36,37,38,39,41,42,43,44,45,47,48,49,50,53,54,55,56,57,60,61,62,64,76,81};
    for(int n:required)if(!item(n))return false;return true;
 }
 case 4:return flag(245)==2;
 case 5:return flag(900)==9;
 case 6:return flag(852)==10;
 case 7:for(int n=85;n<=104;n++)if(!item(n))return false;return true;
 case 8:return flag(808)==45;
 case 9:return mem<unsigned>(0x6e1214)<=144000000;
 case 10:return flag(119)==28;
 case 11:return flag(235)==1;
 case 12:return mem<unsigned>(0x6e1214)<=72000000;
 case 13:return flag(902)==4;
 case 14:return mem<unsigned>(0x6e1214)<=36000000;
 case 15:return flag(262)==2;
 case 16:return flag(903)!=0;
 case 17:return flag(904)==1&&flag(905)==1&&flag(906)==1;
 case 18:return flag(925)==1;
 }return false;
}
static void portrait(int id,int x,int y,bool bright) {
    GdiFlush();
    for(int yy=0;yy<48;yy++)for(int xx=0;xx<48;xx++){
        auto c=PORTRAITS[id][yy*48+xx];int a=c>>24;if(!a)continue;
        int r=(c>>16)&255,g=(c>>8)&255,b=c&255;
        if(!bright){r=r*45/100;g=g*45/100;b=b*45/100;}
        uint32_t& dst=pixels[(y+yy)*640+x+xx];int dr=(dst>>16)&255,dg=(dst>>8)&255,db=dst&255;
        dst=((r*a+dr*(255-a))/255<<16)|((g*a+dg*(255-a))/255<<8)|((b*a+db*(255-a))/255);
    }
}
static void paintRoster() {
    int count=0;for(auto& c:companions)if(rosterReady(c.rule))count++;
    section(20,60,600,286,L"结局角色",200);
    text(29,81,570,L"本档条件  "+std::to_wstring(count)+L" / 26",ink,smallFont);
    for(int n=0;n<ROSTER_COUNT;n++){
        int x=30+n%ROSTER_COLUMNS*65,y=115+n/ROSTER_COLUMNS*76;bool ready=rosterReady(companions[n].rule);
        if(n==selected)cursor(x-3,y-2,55,62);
        portrait(n,x,y,ready);
    }
    section(20,352,600,96,L"同行条件",200);auto& c=companions[selected];bool ready=rosterReady(c.rule);
    int height=inkMetrics(body).height;
    int cy=c.rule==0?middleY(367,80,body):367+(80-(height*2+8))/2;
    text(30,cy,220,c.name,ink);text(267,cy,340,c.rule==0?L"固定出场":c.rule==9||c.rule==12||c.rule==14?(ready?L"尚未超时":L"已超时"):(ready?L"条件已满足":L"条件未满足"),ready?ink:red);
    if(c.rule!=0)text(30,cy+height+8,580,c.condition,ink);
}

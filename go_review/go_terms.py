# -*- coding: utf-8 -*-
"""Go terminology dictionary — the data behind the /terms page.

English Go vocabulary is mostly Japanese loanwords (fuseki, tesuji, atari), which
is why the spelling rarely matches how it is said.  Each entry therefore carries:

    (category, english, chinese, pinyin, say, meaning)

  english  the term as written in English commentary and books
  chinese  the standard Chinese term (kept in Chinese on purpose — this column is
           the whole point of the page)
  pinyin   toneless pinyin for the Chinese, so the page can be searched from an
           English keyboard with no IME
  say      a plain respelling for terms whose pronunciation is not obvious;
           empty for ordinary English words like "ladder" or "blunder"
  meaning  one or two sentences, written for a player who knows the concept in
           Chinese and needs the English label

Pure data, no imports — `web_app.terms_page()` renders it.
"""

# (id, display label) — the order here is the order of sections on the page.
CATEGORIES = [
    ("basics",    "Board &amp; basics"),
    ("opening",   "Opening &amp; joseki"),
    ("moves",     "Common moves"),
    ("shape",     "Shape, connection &amp; thickness"),
    ("lifedeath", "Life &amp; death"),
    ("fighting",  "Fighting &amp; capture"),
    ("ko",        "Ko"),
    ("judgement", "Direction &amp; judgement"),
    ("endgame",   "Endgame (yose)"),
    ("game",      "Playing, etiquette &amp; study"),
    ("metrics",   "This app's own terms"),
]

TERMS = [
    # ---- Board & basics ----------------------------------------------------
    ("basics", "Go / igo / weiqi / baduk", "围棋", "weiqi", "EE-goh",
     "The game itself. English books say <b>Go</b>; <i>igo</i> is Japanese, "
     "<i>weiqi</i> Chinese, <i>baduk</i> Korean. All four mean the same game."),
    ("basics", "Stone", "棋子", "qizi", "",
     "One playing piece. English counts them as stones, never 'pieces'."),
    ("basics", "Liberty", "气", "qi", "",
     "An empty point adjacent to a stone or group. Running out of liberties is "
     "how stones get captured, so 'this group has three liberties' is the most "
     "common phrase in any fighting discussion."),
    ("basics", "Group / chain / string", "棋块 / 一块棋", "qikuai", "",
     "Stones of one colour connected along lines, sharing their liberties. "
     "'Chain' and 'string' mean strictly connected stones; 'group' is looser and "
     "often means stones that work together even if not yet linked."),
    ("basics", "Eye", "眼", "yan", "",
     "An enclosed empty point that the opponent cannot fill. Two eyes make a "
     "group unconditionally alive."),
    ("basics", "False eye", "假眼", "jiayan", "",
     "A point that looks like an eye but collapses because the surrounding "
     "stones can be captured or cut apart."),
    ("basics", "Star point / hoshi", "星", "xing", "HOH-shee",
     "The 4-4 point. English uses both 'star point' and the Japanese "
     "<i>hoshi</i>; 'the 4-4' is just as common in modern writing."),
    ("basics", "3-4 point / komoku", "小目", "xiaomu", "koh-MOH-koo",
     "The 3-4 point — territory-leaning corner opening."),
    ("basics", "3-3 point / san-san", "三三", "sansan", "sahn-SAHN",
     "The 3-3 point. The immediate 3-3 invasion under a star point is the "
     "signature AI-era joseki."),
    ("basics", "5-4 point / takamoku", "高目", "gaomu", "tah-kah-MOH-koo",
     "The 5-4 point — influence-leaning, aims at the outside."),
    ("basics", "5-3 point / mokuhazushi", "目外", "muwai", "moh-koo-hah-ZOO-shee",
     "The 5-3 point. Aims outward like takamoku but keeps a corner "
     "invasion in reserve."),
    ("basics", "Tengen / centre point", "天元", "tianyuan", "TEN-ghen",
     "The exact centre of the board, 10-10."),
    ("basics", "Corner / side / centre", "角 / 边 / 中腹", "jiao bian zhongfu", "",
     "The three regions of the board. English says 'the centre' where Chinese "
     "often says 中腹."),
    ("basics", "First line / second line", "第一线 / 第二线", "diyixian", "",
     "Counted inward from the edge, so the first line is the edge itself. "
     "'Crawling on the second line' is the standard complaint about a bad "
     "endgame exchange."),
    ("basics", "Komi", "贴目", "tiemu", "KOH-mee",
     "Points given to White to offset Black's first-move advantage — 7.5 under "
     "Chinese rules, 6.5 under Japanese."),
    ("basics", "Handicap", "让子", "rangzi", "",
     "Extra stones Black places before play to even out a strength gap. "
     "'A three-stone handicap' = 让三子."),
    ("basics", "Area scoring", "数子法", "shuzifa", "",
     "Chinese rules: you count your stones plus your enclosed empty points. "
     "This is what Fox and KataGo use, which is why captures are not added on "
     "at the end."),
    ("basics", "Territory scoring", "数目法", "shumufa", "",
     "Japanese rules: you count enclosed empty points plus prisoners taken."),
    ("basics", "Dan / kyu", "段 / 级", "duan ji", "dahn / kyoo",
     "Ranks. Kyu numbers fall as you improve (10k to 1k), then dan numbers rise "
     "(1d upward). '3 dan' = 三段."),
    ("basics", "Pass", "弃权 / 虚手", "qiquan", "",
     "Declining to play a stone. Two consecutive passes end the game."),
    ("basics", "Resign", "认输", "renshu", "",
     "Conceding. In English you 'resign' — you never 'lose the game' as a verb."),

    # ---- Opening & joseki -------------------------------------------------
    ("opening", "Fuseki / opening", "布局", "buju", "foo-SEH-kee",
     "The opening phase, while the corners and sides are being staked out. This "
     "app labels the first 40 moves <b>Fuseki</b>."),
    ("opening", "Joseki", "定式", "dingshi", "joh-SEH-kee",
     "An established local sequence, usually in a corner, that both sides "
     "accept as fair. Note: joseki is <i>local</i>; fuseki is the whole board."),
    ("opening", "Corner enclosure / shimari", "守角 / 无忧角", "shoujiao", "shee-MAH-ree",
     "A second stone that secures a corner, e.g. the 小飞守角 (small knight "
     "enclosure)."),
    ("opening", "Approach move / kakari", "挂 / 挂角", "guajiao", "kah-KAH-ree",
     "A move that approaches the opponent's lone corner stone."),
    ("opening", "Pincer / hasami", "夹", "jia", "hah-SAH-mee",
     "Answering an approach by attacking it from the other side, so it is "
     "squeezed between two of your stones."),
    ("opening", "Extension", "拆 / 开拆", "chai", "",
     "Playing along a side at a comfortable distance from your own stones. "
     "'A two-space extension' = 拆二."),
    ("opening", "Double wing formation", "双翼阵势", "shuangyi", "",
     "A corner stone with extensions along both adjacent sides — the classic "
     "ideal shape."),
    ("opening", "Chinese opening / Kobayashi opening", "中国流 / 小林流", "zhongguoliu", "",
     "Named whole-board opening patterns. English keeps the names as-is."),
    ("opening", "Mini-Chinese", "迷你中国流", "mini zhongguoliu", "", "A lower variant of the Chinese opening."),
    ("opening", "Sanrensei", "三连星", "sanlianxing", "sahn-ren-SEH-ee",
     "Three star points in a row on one side — an influence-first opening."),
    ("opening", "Trick play / hamete", "骗招", "pianzhao", "hah-MEH-teh",
     "A move that is objectively bad but sets a trap, punishing a careless "
     "reply."),
    ("opening", "Whole-board opening theory", "全局构思", "quanju gousi", "",
     "The plan behind your opening choices, as opposed to memorised joseki."),

    # ---- Common moves -----------------------------------------------------
    ("moves", "Jump / tobi", "跳", "tiao", "TOH-bee",
     "Leaving one or more empty points along a line. 'One-space jump' = 单关跳, "
     "'two-space jump' = 二间跳."),
    ("moves", "Knight's move / keima", "小飞", "xiaofei", "KEH-ee-mah",
     "The diagonal move shaped like a chess knight's leap. English also says "
     "'the small knight's move'."),
    ("moves", "Large knight's move / ogeima", "大飞", "dafei", "oh-GEH-ee-mah",
     "One step further than keima — faster but thinner."),
    ("moves", "Diagonal move / kosumi", "尖", "jian", "koh-SOO-mee",
     "A move diagonally adjacent to your own stone. Solid and slow."),
    ("moves", "Attachment / tsuke", "靠", "kao", "TSOO-keh",
     "Playing in direct contact with an enemy stone. Contact plays are how you "
     "settle a weak group or provoke a reply."),
    ("moves", "Hane", "扳", "ban", "HAH-neh",
     "A diagonal move played around the head of the opponent's stones, blocking "
     "their advance. 'Double hane' = 双扳."),
    ("moves", "Extension / nobi", "长 / 立", "chang li", "NOH-bee",
     "Solidly extending a stone by one point along the line."),
    ("moves", "Block / osae", "挡", "dang", "oh-SAH-eh",
     "Stopping the opponent from advancing further in your direction."),
    ("moves", "Draw back / hiki", "退", "tui", "HEE-kee",
     "Pulling back one point instead of pressing on — safe but concedes."),
    ("moves", "Push", "冲 / 顶", "chong ding", "",
     "Advancing along a line in contact with enemy stones. 'Pushing from "
     "behind' (从后面推) is the classic mistake of helping the opponent build."),
    ("moves", "Push through and cut", "冲断", "chongduan", "",
     "The two-move combination that breaks a gap apart."),
    ("moves", "Cut / kiri", "断", "duan", "KEE-ree",
     "Playing at a cutting point to separate the opponent into two groups."),
    ("moves", "Crosscut", "扭断", "niuduan", "",
     "Both players cut through each other at once, producing a fight with no "
     "safe answer. 'Crosscut, then extend' is the standard proverb."),
    ("moves", "Connect / tsugi", "连 / 接", "lian jie", "TSOO-ghee",
     "Joining your stones so they share liberties."),
    ("moves", "Solid connection", "实连", "shilian", "",
     "Filling the cutting point outright."),
    ("moves", "Hanging connection / tiger's mouth", "虎口 / 虚连", "hukou", "",
     "Connecting diagonally rather than solidly — lighter, but leaves aji."),
    ("moves", "Wedge / warikomi", "挖", "wa", "wah-ree-KOH-mee",
     "Playing into a one-point gap between two enemy stones."),
    ("moves", "Clamp / hasamitsuke", "夹", "jia", "hah-sah-mee-TSOO-keh",
     "Attaching on both sides of a stone at once."),
    ("moves", "Peep / peek / nozoki", "觑", "qu", "noh-ZOH-kee",
     "Threatening to cut through a hanging connection, forcing the opponent to "
     "fill. Overusing it is ajikeshi."),
    ("moves", "Shoulder hit / katatsuki", "肩冲", "jianchong", "kah-tah-TSOO-kee",
     "Playing diagonally above an enemy stone, typically to reduce a "
     "third-line position."),
    ("moves", "Cap / boshi", "镇 / 帽子", "zhen", "BOH-shee",
     "Playing two points above a stone to block it from the centre."),
    ("moves", "Descent / sagari", "下立 / 沉", "xiali", "sah-GAH-ree",
     "Playing straight down towards the edge, usually to secure liberties or an "
     "eye."),
    ("moves", "Turn / magari", "扳头 / 转", "magari", "mah-GAH-ree",
     "Bending around the head of the opponent's stones."),
    ("moves", "Bump / tsukiatari", "撞 / 顶", "zhuang", "tsoo-kee-ah-TAH-ree",
     "Playing directly into an enemy stone head-on."),
    ("moves", "Placement / oki", "点", "dian", "OH-kee",
     "Playing a stone inside the opponent's area, not in contact with "
     "anything — the classic eye-stealing and life-and-death move."),
    ("moves", "Throw-in", "扑 / 送吃", "pu", "",
     "Deliberately giving a stone to be captured, to remove a liberty or "
     "destroy an eye."),
    ("moves", "Monkey jump / saru-suberi", "猴子脸 / 大飞侵消", "houzilian", "sah-roo-soo-BEH-ree",
     "The large knight's slide along the second line — a big endgame reduction."),

    # ---- Shape, connection & thickness ------------------------------------
    ("shape", "Shape / katachi", "棋形", "qixing", "kah-TAH-chee",
     "The local configuration of your stones, judged by efficiency rather than "
     "point count."),
    ("shape", "Good shape / bad shape", "好形 / 愚形", "haoxing yuxing", "",
     "English says 'bad shape' or 'bad form' for 愚形."),
    ("shape", "Empty triangle", "空三角", "kongsanjiao", "",
     "Three stones in an L with the fourth point empty — the textbook example "
     "of bad shape, because one stone does no work."),
    ("shape", "Ponnuki", "方形（提子后）", "fangxing", "pohn-NOO-kee",
     "The diamond of four stones left after capturing one stone. 'Ponnuki is "
     "worth thirty points' is a standard proverb."),
    ("shape", "Bamboo joint", "双 / 竹节", "shuang", "",
     "Two pairs of stones side by side — uncuttable without being self-"
     "destructive."),
    ("shape", "Table shape", "桌子形", "zhuozixing", "",
     "A three-stone shape whose vital point is the fourth corner."),
    ("shape", "Dumpling / clump", "愚形团子", "tuanzi", "",
     "A solid lump of stones with almost no eye space or efficiency — the worst "
     "outcome of a squeeze."),
    ("shape", "Iron pillar / tetteki", "铁柱", "tiezhu", "teh-TEH-kee",
     "Two stones stacked vertically. Heavy but very solid."),
    ("shape", "Elephant eye", "象眼", "xiangyan", "",
     "The centre point of two diagonally placed stones — a gap that can often "
     "be pierced."),
    ("shape", "Dog's head / horse head", "狗头 / 马头", "goutou matou", "",
     "Named shapes whose vital points are worth memorising."),
    ("shape", "Thickness / atsumi", "厚势", "houshi", "ah-TSOO-mee",
     "A position with no weaknesses, useful for attacking. The English proverb "
     "is 'don't use thickness to make territory'."),
    ("shape", "Thin / thinness", "薄", "bao", "",
     "A position full of cutting points and invasion aims."),
    ("shape", "Light / karui", "轻灵", "qingling", "kah-ROO-ee",
     "Flexible, easily abandoned or resettled — a compliment."),
    ("shape", "Heavy / omoi", "沉重 / 重", "chenzhong", "oh-MOH-ee",
     "A group with no eyes and no escape that must be dragged around — a "
     "criticism."),
    ("shape", "Overconcentrated", "凝形 / 过于集中", "ningxing", "",
     "Too many stones doing the same small job."),
    ("shape", "Sabaki", "腾挪 / 整形", "tengnuo", "sah-BAH-kee",
     "Settling a group lightly inside the opponent's sphere of influence, "
     "usually with contact plays."),
    ("shape", "Tesuji", "手筋", "shoujin", "teh-SOO-jee",
     "A skilful local move that achieves more than the obvious one. Plural is "
     "just 'tesuji'."),
    ("shape", "Suji / vulgar move (zokusuji)", "筋 / 俗筋", "jin sujin", "SOO-jee",
     "<i>Suji</i> is the natural line of play; <i>zokusuji</i> is a crude move "
     "that works locally but spoils your own position."),
    ("shape", "Honte", "本手", "benshou", "HOHN-teh",
     "The proper, solid move — the one that leaves no weakness behind, even "
     "though a faster move exists."),
    ("shape", "Forcing move / kikashi", "先手利用", "xianshou liyong", "kee-KAH-shee",
     "A move the opponent must answer, played to gain something before "
     "resuming elsewhere."),
    ("shape", "Sente", "先手", "xianshou", "SEN-teh",
     "Holding the initiative: your move demands an answer, so you get to play "
     "next elsewhere too."),
    ("shape", "Gote", "后手", "houshou", "GOH-teh",
     "Ending in a position where the opponent gets the next free move."),
    ("shape", "Tenuki", "脱先", "tuoxian", "teh-NOO-kee",
     "Ignoring the local exchange and playing the bigger point elsewhere. "
     "Failing to tenuki is the most common amateur habit."),
    ("shape", "Miai", "见合 / 两处等价", "jianhe", "MEE-ah-ee",
     "Two points of equal value: if the opponent takes one, you take the other, "
     "so neither is urgent."),
    ("shape", "Trade / exchange / furikawari", "转换", "zhuanhuan", "foo-ree-kah-WAH-ree",
     "Giving up one thing to take another of comparable size — the main tool "
     "when you are behind."),
    ("shape", "Aji", "余味 / 味道", "yuwei", "AH-jee",
     "Latent potential in a position: cuts and placements you have not played "
     "yet but might."),
    ("shape", "Ajikeshi", "消味", "xiaowei", "AH-jee-keh-shee",
     "Spoiling your own aji by cashing in a threat too early, usually with a "
     "pointless peep or forcing move."),
    ("shape", "Probe / yosu-miru", "试应手", "shiyingshou", "YOH-soo-MEE-roo",
     "A move played to see how the opponent answers before you commit to a "
     "plan."),
    ("shape", "Sacrifice", "弃子", "qizi", "",
     "Giving stones up on purpose for a bigger gain elsewhere."),

    # ---- Life & death -----------------------------------------------------
    ("lifedeath", "Life and death", "死活", "sihuo", "",
     "Whether a group can make two eyes. English keeps 'life and death' as one "
     "fixed phrase."),
    ("lifedeath", "Alive / dead", "活 / 死", "huo si", "",
     "'This group is alive' = 这块棋活了. 'Dead as it stands' = 净死."),
    ("lifedeath", "Unconditionally alive", "净活", "jinghuo", "",
     "Alive with no ko, no conditions, nothing left to try."),
    ("lifedeath", "Seki / mutual life", "双活 / 共活", "shuanghuo", "SEH-kee",
     "Neither group can capture the other without dying first, so both live "
     "with fewer than two eyes."),
    ("lifedeath", "Eye space", "眼位", "yanwei", "",
     "The enclosed area a group has to work with when trying to make eyes."),
    ("lifedeath", "Vital point of a shape", "要点 / 急所", "yaodian", "",
     "The single point that decides life or death — 'the vital point' in "
     "English, whether attacking or defending."),
    ("lifedeath", "Straight three / bent three", "直三 / 曲三", "zhisan qusan", "",
     "The basic dead three-space shapes; the killing move is the middle point."),
    ("lifedeath", "Straight four / bent four", "直四 / 曲四", "zhisi qusi", "",
     "Alive as they stand. But 'bent four in the corner' (角上曲四) is dead."),
    ("lifedeath", "Square four", "方四", "fangsi", "",
     "Dead — four in a block cannot make two eyes."),
    ("lifedeath", "Bulky five / crossed five", "刀把五 / 梅花五", "daobawu meihuawu", "",
     "Five-space shapes that die to a placement at the centre. 'Crossed five' "
     "is also called 'flowery five'."),
    ("lifedeath", "Rectangular six / bulky six", "板六", "banliu", "",
     "Alive in the open, dead in the corner — the classic exception to learn."),
    ("lifedeath", "Big eye / nakade", "大眼杀 / 中手", "dayansha", "nah-KAH-deh",
     "A large enclosed space that is still only one eye, because the defender "
     "must fill it themselves."),
    ("lifedeath", "Snapback", "倒扑", "daopu", "",
     "Letting the opponent capture, then immediately recapturing a larger "
     "group. One of the first tesuji everyone learns."),
    ("lifedeath", "Under the stones", "石下 / 倒脱靴", "shixia", "",
     "A rare tesuji where you let stones be captured, then play back into the "
     "emptied space to kill."),
    ("lifedeath", "Eye-stealing tesuji", "破眼手筋", "poyan shoujin", "",
     "A move that removes the opponent's eye shape rather than their liberties."),
    ("lifedeath", "Shortage of liberties / damezumari", "气紧", "qijin", "dah-meh-zoo-MAH-ree",
     "Losing a fight purely because your own stones run out of liberties first. "
     "Worth flagging in your reviews — it is a reading failure, not a judgement "
     "one."),
    ("lifedeath", "One-eye versus no-eye", "有眼杀无眼", "youyan sha wuyan", "",
     "In a capturing race, the side with an eye wins even at equal liberties."),
    ("lifedeath", "Connect and die / oiotoshi", "连回不归", "lianhui bugui", "oh-ee-oh-TOH-shee",
     "Connecting your stones only makes the whole chain capturable in one go."),
    ("lifedeath", "Ten thousand year ko", "万年劫", "wannianjie", "",
     "A ko-ish shape neither side wants to start, usually left until the very "
     "end of the game."),
    ("lifedeath", "Tsumego / life-and-death problem", "死活题", "sihuoti", "tsoo-meh-GOH",
     "A set problem where you find the killing or living move. The standard "
     "English word for 做死活题."),

    # ---- Fighting & capture -----------------------------------------------
    ("fighting", "Atari", "打吃", "dachi", "ah-TAH-ree",
     "A move that leaves an enemy group with one liberty — one more move and it "
     "is captured. Used as a verb too: 'he ataried the cutting stone'."),
    ("fighting", "Double atari", "双打吃", "shuangdachi", "",
     "One move putting two separate groups in atari; one of them must fall."),
    ("fighting", "Counter-atari", "反打", "fanda", "",
     "Answering an atari with an atari of your own instead of connecting."),
    ("fighting", "Capture", "提子", "tizi", "",
     "Removing stones with no liberties left. The captured stones are "
     "'prisoners'."),
    ("fighting", "Ladder / shicho", "征子", "zhengzi", "shee-CHOH",
     "A running sequence of ataris along a diagonal staircase. It works or "
     "fails depending on what waits at the far corner."),
    ("fighting", "Ladder breaker", "引征 / 征子有利", "yinzheng", "",
     "A stone placed in the ladder's path so the ladder no longer works."),
    ("fighting", "Loose ladder / yurumi shicho", "宽征", "kuanzheng", "yoo-ROO-mee shee-CHOH",
     "A ladder with slack in it — the pursued stones stay caught but are not in "
     "atari every move."),
    ("fighting", "Net / geta", "罩 / 飞罩", "zhao feizhao", "GEH-tah",
     "Capturing stones by enclosing them loosely rather than chasing with "
     "atari. Often the right answer when the ladder fails."),
    ("fighting", "Capturing race / semeai", "对杀", "duisha", "seh-meh-AH-ee",
     "Two adjacent groups both short of eyes, racing to fill each other's "
     "liberties. Count before you play."),
    ("fighting", "Inside / outside liberties", "内气 / 外气", "neiqi waiqi", "",
     "In a capturing race, shared inside liberties belong to whoever fills the "
     "outside ones first."),
    ("fighting", "Dame / neutral point", "单官 / 公气", "danguan gongqi", "DAH-meh",
     "A point worth nothing to either side. 'Filling dame' is the last stage of "
     "the game."),
    ("fighting", "Squeeze / shibori", "滚打包收", "gundabaoshou", "shee-BOH-ree",
     "A forcing sequence of sacrifices that leaves the opponent in a dumpling "
     "with no eyes."),
    ("fighting", "Cutting stone", "断点上的子", "duandian", "",
     "The stone whose capture would reconnect the opponent. English distinguishes "
     "cutting stones from expendable stones sharply — 'never lose your cutting "
     "stones'."),
    ("fighting", "Splitting attack", "分断攻击", "fenduan gongji", "",
     "Playing between two weak enemy groups so neither can be defended "
     "comfortably."),
    ("fighting", "Leaning attack / motare", "倚盖 / 靠攻", "yigai", "moh-TAH-reh",
     "Attacking a strong group first, purely to build strength for the real "
     "attack on a weak one."),
    ("fighting", "Driving / driving tesuji", "驱赶", "qugan", "",
     "Forcing an enemy group to run in the direction that suits you."),
    ("fighting", "Chase / pursue", "追", "zhui", "",
     "'Chasing' a weak group to profit while it runs. In English you attack "
     "groups 'for profit', rarely to kill."),
    ("fighting", "Escape / run out", "逃 / 跑出", "tao paochu", "",
     "Getting a weak group into the open centre."),
    ("fighting", "Invasion", "打入", "daru", "",
     "Playing inside the opponent's framework to live or to run out."),
    ("fighting", "Reduction / erasure", "侵消 / 削减", "qinxiao", "",
     "Shrinking the opponent's area from outside instead of invading. English "
     "contrasts 'invade' with 'reduce' constantly."),

    # ---- Ko ---------------------------------------------------------------
    ("ko", "Ko", "劫", "jie", "koh",
     "A shape where recapturing immediately would repeat the position, so you "
     "must play elsewhere first."),
    ("ko", "Ko fight", "劫争", "jiezheng", "",
     "The exchange of threats and answers around a ko."),
    ("ko", "Ko threat", "劫材", "jiecai", "",
     "A move the opponent must answer, played so you can then retake the ko. "
     "English also says 'ko ban' (from the Japanese)."),
    ("ko", "Local ko threat", "本身劫材", "benshen jiecai", "",
     "A threat inside the ko shape itself, so it does not cost you elsewhere."),
    ("ko", "Flower-viewing ko / hanami ko", "无忧劫 / 花见劫", "wuyoujie", "hah-NAH-mee koh",
     "A ko one side risks nothing in and the other side could lose the game "
     "on."),
    ("ko", "Double ko", "双劫", "shuangjie", "",
     "Two kos in one shape — often an unkillable position."),
    ("ko", "Triple ko", "三劫循环", "sanjie xunhuan", "",
     "Three kos cycling with no resolution; under most rules the game is void "
     "or repeated."),
    ("ko", "Send two return one", "送二还一", "songer huanyi", "",
     "A ko-related shape where sacrificing two stones lets you retake one, "
     "repeatedly."),
    ("ko", "Answer the ko / respond", "应劫", "yingjie", "",
     "Replying to a ko threat rather than taking the ko."),

    # ---- Direction & judgement --------------------------------------------
    ("judgement", "Big point", "大场", "dachang", "",
     "The largest open area on the board. 'Missing the big point' is the single "
     "most common diagnosis in this app's blunder set."),
    ("judgement", "Vital point / kyusho", "急所", "jisuo", "KYOO-shoh",
     "The urgent point — the one that must be played now, whatever its size. "
     "The proverb is 'urgent before big' (急所先于大场)."),
    ("judgement", "Direction of play", "方向 / 大方向", "fangxiang", "",
     "Which way to face when you attack or extend. English treats this as a "
     "concept in its own right: 'the direction of play is wrong'."),
    ("judgement", "Whole-board thinking", "全局观 / 全局判断", "quanjuguan", "",
     "Weighing the whole board before choosing a local move."),
    ("judgement", "Positional judgement", "形势判断", "xingshi panduan", "",
     "Estimating who is ahead and by how much, to decide whether to play safe "
     "or to fight."),
    ("judgement", "Counting", "数目", "shumu", "",
     "Adding up territory to get a number. 'Count around move 100' is standard "
     "advice."),
    ("judgement", "Moyo / framework", "模样 / 阵势", "moyang zhenshi", "MOH-yoh",
     "A large loose area that is not yet territory but is leaning your way."),
    ("judgement", "Territory versus influence", "实地与模样", "shidi yu moyang", "",
     "The central strategic trade-off of the opening."),
    ("judgement", "Sphere of influence", "势力范围", "shili fanwei", "",
     "The region your stones dominate, where fighting favours you."),
    ("judgement", "Efficiency", "效率", "xiaolv", "",
     "How much work each stone does. Most 'bad shape' criticism is really an "
     "efficiency argument."),
    ("judgement", "Slack move / slow move", "缓手", "huanshou", "",
     "A move that is not wrong but is smaller than what was available. English "
     "says 'slack' or 'slow'."),
    ("judgement", "Overplay", "过分", "guofen", "",
     "Trying for more than the position allows, and inviting punishment."),
    ("judgement", "Bad move", "恶手", "eshou", "",
     "Actively wrong, not merely small."),
    ("judgement", "Simplify", "简明化", "jianminghua", "",
     "Choosing the plain, safe line when you are ahead. This is the fix for a "
     "low lead conversion, and the phrase you want in English reviews."),
    ("judgement", "Play safe / take the sure thing", "求稳", "qiuwen", "",
     "Cashing your advantage instead of fighting on."),
    ("judgement", "Game-turning move / do-or-die move", "胜负手", "shengfushou", "",
     "A move played when losing, that either recovers everything or ends it."),
    ("judgement", "Aim / follow-up", "后续手段", "houxu shouduan", "",
     "What a move threatens next. English says 'this move aims at the cut'."),
    ("judgement", "Endgame is where games are lost", "官子定胜负", "guanzi ding shengfu", "",
     "A common English framing of the same idea as 官子无小事 — small endgame "
     "errors decide close games."),

    # ---- Endgame ----------------------------------------------------------
    ("endgame", "Yose / endgame", "官子 / 收官", "guanzi shouguan", "YOH-seh",
     "The final phase, where boundaries are settled. This app labels the last "
     "stretch of each game <b>Yose</b>."),
    ("endgame", "Double sente", "双方先手 / 双先", "shuangxian", "",
     "An endgame play that is sente for whoever takes it first — so take it "
     "early, before it becomes gote."),
    ("endgame", "Reverse sente", "逆先手", "nixianshou", "",
     "Playing gote yourself to deny the opponent a sente move. Worth about "
     "twice its face value."),
    ("endgame", "Gote endgame play", "后手官子", "houshou guanzi", "",
     "The opponent gets the next move, so take these largest-first."),
    ("endgame", "Hane and connect", "扳粘", "banzhan", "",
     "The standard two-move edge endgame sequence."),
    ("endgame", "Tedomari", "收后 / 最后一手", "shouhou", "teh-doh-MAH-ree",
     "Getting the last meaningful play before only dame remain — often worth a "
     "point or two on its own."),
    ("endgame", "Half point", "半目", "banmu", "",
     "The smallest unit under Japanese counting; 'losing by half a point' is "
     "the classic heartbreak."),
    ("endgame", "Endgame value", "官子价值", "guanzi jiazhi", "",
     "The points a play gains, used to order the endgame. English writes "
     "'this is worth 8 points in gote'."),
    ("endgame", "Fill dame", "收单官", "shou danguan", "",
     "Filling the last neutral points before counting."),
    ("endgame", "Seal the border", "收边 / 补断点", "shoubian", "",
     "Closing your boundary so there is nothing left to exploit."),

    # ---- Playing, etiquette & study ---------------------------------------
    ("game", "Nigiri", "猜先", "caixian", "nee-GEE-ree",
     "Guessing odd or even with stones to decide who takes Black."),
    ("game", "Byo-yomi", "读秒", "dumiao", "BYOH-yoh-mee",
     "Overtime counting after your main time runs out."),
    ("game", "Main time / period", "基本时限 / 保留时间", "jibenshixian", "",
     "'Sudden death' means no byo-yomi at all — 包干."),
    ("game", "Kifu / game record", "棋谱", "qipu", "KEE-foo",
     "The record of a game. An SGF file is a kifu."),
    ("game", "Review a game", "复盘", "fupan", "",
     "Going back through a finished game. English says 'review the game' or "
     "'go over the game' — never 'repeat the board'."),
    ("game", "Post-game discussion", "复盘讨论", "fupan taolun", "",
     "The conversation after a game. The Japanese term is <i>kenshu</i>."),
    ("game", "Joseki dictionary", "定式辞典", "dingshi cidian", "",
     "A reference of standard corner sequences."),
    ("game", "Proverb", "格言 / 口诀", "geyan koujue", "",
     "The short rules of thumb: 'play the vital point before the big point', "
     "'don't use thickness to make territory'."),
    ("game", "Insei", "院生", "yuansheng", "IN-seh-ee",
     "A pupil in a professional training academy."),
    ("game", "Pro / amateur", "职业 / 业余", "zhiye yeyu", "",
     "'5p' means 5-dan professional; '5d' amateur 5-dan."),
    ("game", "Teaching game", "指导棋", "zhidaoqi", "",
     "A game played to instruct rather than to win."),
    ("game", "Rating / rank", "等级分 / 段位", "dengjifen duanwei", "",
     "Fox shows both a rank and an internal rating."),

    # ---- This app's own terms ---------------------------------------------
    ("metrics", "Blunder", "大错", "dacuo", "",
     "In this app: a move losing <b>&ge;6 points</b> <i>or</i> dropping your win "
     "rate by <b>&ge;15%</b>. The two triggers are a union, so a move can be a "
     "blunder on either count alone."),
    ("metrics", "Mistake", "失误 / 错着", "shiwu", "",
     "A smaller error — the app's mistake threshold is 2 points by default."),
    ("metrics", "Points lost", "损失目数", "sunshi mushu", "",
     "KataGo's score for its best move minus its score for the move you "
     "actually played. The core number in every chart here."),
    ("metrics", "Win rate", "胜率", "shenglv", "",
     "KataGo's estimate of your chance of winning. Curves in this app are "
     "flipped to your colour, so above 50% always means you are ahead."),
    ("metrics", "Score lead", "目数领先", "mushu lingxian", "",
     "The expected final margin in points, komi included. KataGo calls it "
     "<i>scoreLead</i>."),
    ("metrics", "Lead conversion", "守成率", "shouchenglv", "",
     "Of the games you entered a phase clearly winning (win rate &ge;90%), the "
     "share you actually won. Low conversion is the fastest thing to fix."),
    ("metrics", "Comeback rate", "逆转率", "nizhuanlv", "",
     "Of the games you entered a phase clearly losing (&le;10%), the share you "
     "still turned around."),
    ("metrics", "Trajectory", "对局走势", "duiju zoushi", "",
     "The shape of your win-rate curve over a game, classified as led "
     "throughout, comeback win, lead thrown away, endgame collapse, and so on."),
    ("metrics", "Ownership / territory estimate", "归属 / 目数估计", "guishu", "",
     "KataGo's per-point guess at who will own each intersection. The app draws "
     "it as squares whose size is the confidence."),
    ("metrics", "Principal variation (PV)", "主要变化 / AI 线路", "zhuyao bianhua", "",
     "The sequence KataGo expects after its recommended move — shown as the "
     "numbered stones on each blunder diagram."),
    ("metrics", "Visits", "计算量", "jisuanliang", "",
     "How many positions KataGo reads per move. More visits means a more "
     "reliable verdict and a slower analysis; 300 is this app's default."),
    ("metrics", "Phase mean", "阶段均值", "jieduan junzhi", "",
     "A move-weighted average: every move from every game pooled, then divided "
     "by the number of moves — not the average of the per-game dots."),
    ("metrics", "Mastered / to review", "已掌握 / 待掌握", "yizhangwo", "",
     "The blunder set's status filter. Mastered is stored in your browser; "
     "deleting a blunder is stored in the report folder."),
]


def count():
    return len(TERMS)


def by_category():
    """[(cat_id, label, [entries...])] in CATEGORIES order, empties dropped."""
    out = []
    for cid, label in CATEGORIES:
        rows = [t for t in TERMS if t[0] == cid]
        if rows:
            out.append((cid, label, rows))
    return out

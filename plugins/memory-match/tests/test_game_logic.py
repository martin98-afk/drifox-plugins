"""记忆翻牌核心逻辑测试"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ui.game_logic import MemoryMatchGame, CardState, GameState


def test_init():
    """测试游戏初始化"""
    game = MemoryMatchGame(4, 4)
    assert game.rows == 4
    assert game.cols == 4
    assert game.total_pairs == 8
    assert game.state == GameState.READY
    assert game.matched_pairs == 0
    assert game.moves == 0


def test_init_invalid_dimensions():
    """测试无效尺寸检测"""
    try:
        MemoryMatchGame(0, 4)
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "正" in str(e)

    try:
        MemoryMatchGame(3, 3)  # 3x3=9 是奇数
        assert False, "应该抛出 ValueError"
    except ValueError as e:
        assert "偶数" in str(e)


def test_start_game():
    """测试开始游戏"""
    game = MemoryMatchGame(4, 4)
    game.start()
    assert game.state == GameState.PLAYING
    assert game.matched_pairs == 0

    # 检查所有卡牌都被正确分配
    total_cards = 0
    emoji_count = {}
    for r in range(4):
        for c in range(4):
            emoji = game._cards[r][c]
            assert emoji is not None
            emoji_count[emoji] = emoji_count.get(emoji, 0) + 1
            total_cards += 1

    assert total_cards == 16
    # 每种 emoji 恰好两张
    for emoji, count in emoji_count.items():
        assert count == 2, f"emoji {emoji} 出现次数为 {count}，应为 2"


def test_flip_first_card():
    """测试翻第一张牌"""
    game = MemoryMatchGame(4, 4)
    game.start()

    result = game.flip(0, 0)
    assert result["game_over"] is False
    assert result["won"] is False
    assert result["first_card"] == (0, 0)
    assert result["second_card"] is None
    assert result["is_match"] is None

    # 第一张牌应该是翻开状态
    assert game.get_card(0, 0)["state"] == CardState.FLIPPED


def test_flip_same_card_twice():
    """测试同一张牌不能翻两次"""
    game = MemoryMatchGame(4, 4)
    game.start()

    result = game.flip(0, 0)
    assert len(result["changed"]) == 1

    # 再次翻同一张牌应该无效
    result = game.flip(0, 0)
    assert len(result["changed"]) == 0


def test_matching_pair():
    """测试配对成功"""
    game = MemoryMatchGame(2, 2)  # 2x2 = 2对
    game.start()

    # 找出配对的两个位置
    emoji0 = game._cards[0][0]
    pair_positions = []
    for r in range(2):
        for c in range(2):
            if game._cards[r][c] == emoji0:
                pair_positions.append((r, c))

    assert len(pair_positions) == 2

    # 翻开第一张
    game.flip(pair_positions[0][0], pair_positions[0][1])
    # 翻开第二张（配对）
    result = game.flip(pair_positions[1][0], pair_positions[1][1])

    assert result["is_match"] is True
    # 注意：2x2 有 2 对，只配对 1 对不会赢
    assert game.matched_pairs == 1
    assert game.moves == 1

    # 配对的牌状态应为 MATCHED
    for r, c in pair_positions:
        assert game.get_card(r, c)["state"] == CardState.MATCHED


def test_non_matching_pair():
    """测试配对失败"""
    game = MemoryMatchGame(2, 2)
    game.start()

    # 找出不同的两个位置
    pos1 = (0, 0)
    pos2 = (0, 1)
    emoji1 = game._cards[pos1[0]][pos1[1]]
    emoji2 = game._cards[pos2[0]][pos2[1]]

    if emoji1 == emoji2:
        # 找不同的
        pos2 = (1, 0)
        emoji2 = game._cards[1][0]

    # 翻开两张不配对的牌
    game.flip(pos1[0], pos1[1])
    result = game.flip(pos2[0], pos2[1])

    assert result["is_match"] is False
    assert result["game_over"] is False
    assert result["won"] is False
    assert game.moves == 1

    # 牌应该保持翻开状态（等待翻回）
    assert game.get_card(pos1[0], pos1[1])["state"] == CardState.FLIPPED
    assert game.get_card(pos2[0], pos2[1])["state"] == CardState.FLIPPED


def test_flip_back():
    """测试翻回操作"""
    game = MemoryMatchGame(2, 2)
    game.start()

    # 找出不配对的两张牌
    pos1 = (0, 0)
    pos2 = (0, 1)
    emoji1 = game._cards[0][0]
    emoji2 = game._cards[0][1]

    if emoji1 == emoji2:
        pos2 = (1, 0)
        emoji2 = game._cards[1][0]
        if emoji1 == emoji2:
            pos2 = (1, 1)
            emoji2 = game._cards[1][1]

    game.flip(pos1[0], pos1[1])
    game.flip(pos2[0], pos2[1])

    # 翻回
    game.flip_back_pair(pos1[0], pos1[1], pos2[0], pos2[1])

    # 应该回到隐藏状态
    assert game.get_card(pos1[0], pos1[1])["state"] == CardState.HIDDEN
    assert game.get_card(pos2[0], pos2[1])["state"] == CardState.HIDDEN
    assert game.state == GameState.PLAYING


def test_reset():
    """测试重置游戏"""
    game = MemoryMatchGame(4, 4)
    game.start()
    game.flip(0, 0)
    game.flip(0, 1)
    game._matched_count = 1
    game._moves = 1

    game.reset()

    assert game.state == GameState.READY
    assert game.matched_pairs == 0
    assert game.moves == 0


def test_timer_and_moves():
    """测试计时和步数统计"""
    game = MemoryMatchGame(4, 4)
    game.start()

    assert game.seconds == 0
    game.seconds = 30
    assert game.seconds == 30

    # 翻一对
    emoji0 = game._cards[0][0]
    pos2 = None
    for r in range(4):
        for c in range(4):
            if (r, c) != (0, 0) and game._cards[r][c] == emoji0:
                pos2 = (r, c)
                break
        if pos2:
            break

    if pos2:
        game.flip(0, 0)
        game.flip(pos2[0], pos2[1])
        assert game.moves == 1


def test_all_pairs_matched():
    """测试全部配对完成"""
    game = MemoryMatchGame(2, 2)  # 2对
    game.start()

    # 收集所有配对
    emojis = {}
    for r in range(2):
        for c in range(2):
            emoji = game._cards[r][c]
            if emoji not in emojis:
                emojis[emoji] = []
            emojis[emoji].append((r, c))

    # 依次配对
    for i, (emoji, positions) in enumerate(emojis.items()):
        game.flip(positions[0][0], positions[0][1])
        result = game.flip(positions[1][0], positions[1][1])
        # 只有最后一对配对后才赢
        if i == len(emojis) - 1:
            assert result["won"] is True

    assert game.matched_pairs == 2
    assert game.state == GameState.WON


if __name__ == "__main__":
    test_init()
    print("✅ test_init")
    test_init_invalid_dimensions()
    print("✅ test_init_invalid_dimensions")
    test_start_game()
    print("✅ test_start_game")
    test_flip_first_card()
    print("✅ test_flip_first_card")
    test_flip_same_card_twice()
    print("✅ test_flip_same_card_twice")
    test_matching_pair()
    print("✅ test_matching_pair")
    test_non_matching_pair()
    print("✅ test_non_matching_pair")
    test_flip_back()
    print("✅ test_flip_back")
    test_reset()
    print("✅ test_reset")
    test_timer_and_moves()
    print("✅ test_timer_and_moves")
    test_all_pairs_matched()
    print("✅ test_all_pairs_matched")
    print("\n🎉 All tests passed!")
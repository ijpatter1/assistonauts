"""Tests for the deterministic scaling system."""

from assistonauts.expeditions.scaling import AgentPool, ScalingManager
from assistonauts.models.config import AutoScaleConfig, ScalingConfig


class TestAgentPool:
    def test_acquire_instance(self) -> None:
        pool = AgentPool(agent_type="compiler", max_instances=3)
        instance_id = pool.acquire()
        assert instance_id is not None
        assert pool.active_count() == 1

    def test_release_instance(self) -> None:
        pool = AgentPool(agent_type="compiler", max_instances=3)
        iid = pool.acquire()
        assert iid is not None
        pool.release(iid)
        assert pool.active_count() == 0

    def test_max_instances_enforced(self) -> None:
        pool = AgentPool(agent_type="compiler", max_instances=2)
        pool.acquire()
        pool.acquire()
        assert pool.acquire() is None
        assert pool.active_count() == 2

    def test_release_frees_slot(self) -> None:
        pool = AgentPool(agent_type="compiler", max_instances=1)
        iid = pool.acquire()
        assert iid is not None
        pool.release(iid)
        assert pool.acquire() is not None


class TestScalingManager:
    def test_singleton_enforcement(self) -> None:
        config = ScalingConfig(
            agents={"scout": "auto", "compiler": "auto"},
            auto_scale=AutoScaleConfig(max_instances=3),
        )
        mgr = ScalingManager(config)

        # Singletons get exactly 1 instance
        assert mgr.acquire("captain") is not None
        assert mgr.acquire("captain") is None

        assert mgr.acquire("curator") is not None
        assert mgr.acquire("curator") is None

        assert mgr.acquire("inspector") is not None
        assert mgr.acquire("inspector") is None

    def test_scalable_agents(self) -> None:
        config = ScalingConfig(
            agents={"scout": "auto", "compiler": "auto"},
            auto_scale=AutoScaleConfig(max_instances=2),
        )
        mgr = ScalingManager(config)

        id1 = mgr.acquire("compiler")
        id2 = mgr.acquire("compiler")
        assert id1 is not None
        assert id2 is not None
        assert mgr.acquire("compiler") is None  # at max

    def test_release(self) -> None:
        config = ScalingConfig(
            agents={"compiler": "auto"},
            auto_scale=AutoScaleConfig(max_instances=1),
        )
        mgr = ScalingManager(config)

        iid = mgr.acquire("compiler")
        assert iid is not None
        mgr.release("compiler", iid)
        assert mgr.acquire("compiler") is not None

    def test_should_scale_up(self) -> None:
        config = ScalingConfig(
            agents={"compiler": "auto"},
            auto_scale=AutoScaleConfig(
                trigger="queue_depth > 5",
                max_instances=3,
            ),
        )
        mgr = ScalingManager(config)
        assert not mgr.should_scale_up("compiler", queue_depth=3)
        assert mgr.should_scale_up("compiler", queue_depth=6)

    def test_should_not_scale_singletons(self) -> None:
        config = ScalingConfig(
            agents={},
            auto_scale=AutoScaleConfig(
                trigger="queue_depth > 5",
                max_instances=3,
            ),
        )
        mgr = ScalingManager(config)
        assert not mgr.should_scale_up(
            "captain",
            queue_depth=100,
        )

    def test_active_counts(self) -> None:
        config = ScalingConfig(
            agents={"scout": "auto", "compiler": "auto"},
            auto_scale=AutoScaleConfig(max_instances=3),
        )
        mgr = ScalingManager(config)
        mgr.acquire("scout")
        mgr.acquire("compiler")
        mgr.acquire("compiler")

        counts = mgr.active_counts()
        assert counts["scout"] == 1
        assert counts["compiler"] == 2

    def test_cooldown_blocks_rapid_scale_up(self) -> None:
        config = ScalingConfig(
            agents={"compiler": "auto"},
            auto_scale=AutoScaleConfig(
                trigger="queue_depth > 2",
                max_instances=3,
                cooldown_minutes=10,  # 10 minutes
            ),
        )
        mgr = ScalingManager(config)
        # First call: should trigger (no prior scale-up)
        assert mgr.should_scale_up("compiler", queue_depth=5)
        mgr.record_scale_up("compiler")
        # Immediate second call: blocked by cooldown
        assert not mgr.should_scale_up("compiler", queue_depth=5)

    def test_unknown_agent_gets_singleton(self) -> None:
        config = ScalingConfig(agents={})
        mgr = ScalingManager(config)
        # Unknown agents default to singleton behavior
        assert mgr.acquire("unknown_agent") is not None
        assert mgr.acquire("unknown_agent") is None

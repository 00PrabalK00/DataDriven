function K = payloadKbox(cfg)
%PAYLOADKBOX Bluff-body drag area of the payload: Cd times the plan-view area of its bounding box.
lo = cfg.payload.extent_min_m; hi = cfg.payload.extent_max_m;
K = cfg.payload.Cd_box * (hi(1) - lo(1)) * (hi(2) - lo(2));
end

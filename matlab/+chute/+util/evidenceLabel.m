function s = evidenceLabel(level)
%EVIDENCELABEL Standard evidence-level tag printed on every figure/table.
switch upper(level)
    case 'L1', s = 'L1 software validation (synthetic truth)';
    case 'L2', s = 'L2 synthetic benchmark under assumed aerodynamics';
    case 'L3', s = 'L3 calibrated-model prediction';
    case 'L4', s = 'L4 physical demonstration';
    otherwise, error('chute:evidence', 'unknown evidence level %s', level);
end
end

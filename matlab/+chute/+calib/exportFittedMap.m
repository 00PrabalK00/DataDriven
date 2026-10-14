function file = exportFittedMap(models, featureNames, version, file)
%EXPORTFITTEDMAP Write a calibration fit (linear models per aero parameter) in the JSON format read
%by python chutesim.aeromap.FittedMap. models: struct, field = parameter name (e.g. K_open_m2),
%value = LinearModel fitted on columns named featureNames. Any refit is a NEW version and needs fresh
%validation (log it with chute.calib.logIteration).
spec.version = version; spec.evidence_level = 'L3'; spec.linear = struct();
fn = fieldnames(models);
for k = 1:numel(fn)
    c = models.(fn{k}).Coefficients.Estimate;
    b = struct();
    for j = 1:numel(featureNames), b.(featureNames{j}) = c(j+1); end
    spec.linear.(fn{k}) = struct('b0', c(1), 'b', b);
end
fid = fopen(file, 'w'); fprintf(fid, '%s', jsonencode(spec, PrettyPrint=true)); fclose(fid);
end

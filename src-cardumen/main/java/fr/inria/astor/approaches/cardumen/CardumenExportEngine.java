package fr.inria.astor.approaches.cardumen;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import com.martiansoftware.jsap.JSAPException;

import fr.inria.astor.core.entities.ModificationPoint;
import fr.inria.astor.core.entities.OperatorInstance;
import fr.inria.astor.core.entities.ProgramVariant;
import fr.inria.astor.core.entities.SuspiciousModificationPoint;
import fr.inria.astor.core.manipulation.MutationSupporter;
import fr.inria.astor.core.setup.ConfigurationProperties;
import fr.inria.astor.core.setup.ProjectRepairFacade;
import fr.inria.main.AstorOutputStatus;
import spoon.reflect.code.CtExpression;
import spoon.reflect.code.CtFieldRead;
import spoon.reflect.code.CtFieldWrite;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtVariableAccess;
import spoon.reflect.declaration.CtField;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;
import spoon.reflect.declaration.CtVariable;
import spoon.reflect.reference.CtArrayTypeReference;
import spoon.reflect.reference.CtExecutableReference;
import spoon.reflect.reference.CtFieldReference;
import spoon.reflect.reference.CtTypeReference;
import spoon.reflect.visitor.filter.TypeFilter;

/**
 * Cardumen variant that exports mined templates, in-scope context (variables and methods),
 * and suspicious-location type information to files for use by external tools.
 * <p>
 * Iterates over suspicious modification points: each iteration overwrites
 * context.txt / target_type.txt for the selected location, invokes the Julia tool
 * (if configured), and tests each returned candidate. Stops on the first patch
 * that passes tests, or after at most {@code maxGeneration} iterations (or sooner
 * if the suspicious-point list is exhausted).
 * <p>
 * By default ({@code modificationpointnavigation=weight}) locations are
 * visited in weighted-random order without replacement, weighted by their
 * suspiciousness score. Pass {@code -suspiciousnavigation inorder} to walk
 * them strictly in descending suspiciousness order, or {@code random} for
 * uniform random selection.
 * <p>
 * Outputs (relative to the working directory):
 *   templates.txt      - written by the ingredient space during setup (one template per line)
 *   context.txt        - in-scope variables and methods at the current modification point
 *   target_type.txt    - location and expression type of the current modification point
 *   type_hierarchy.txt - superclass and interface relations for types appearing in templates
 * Only the last iteration's context.txt / target_type.txt / julia_output.txt survive on disk.
 * <p>
 * Invoke via:
 *   -mode custom -customengine fr.inria.astor.approaches.cardumen.CardumenExportEngine
 */
public class CardumenExportEngine extends CardumenApproach {

    private static final String CANDIDATE_EXPRESSION = "0";
    private static final String CANDIDATE_PREFIX = "Testing candidate: ";

    /** Universal key for any array `.length` access, regardless of element type. */
    private static final String ARRAY_LENGTH_KEY = "array#length";

    private List<String> lastCandidates = new ArrayList<>();

    public List<String> getLastCandidates() { return lastCandidates; }

    public CardumenExportEngine(MutationSupporter mutatorExecutor, ProjectRepairFacade projFacade)
            throws JSAPException {
        super(mutatorExecutor, projFacade);
    }

    @Override
    public void startSearch() throws Exception {
        // templates.txt is already written by ExpressionTypeIngredientSpace.defineSpace()
        // which runs during loadExtensionPoints() before this method is called.

        List<ModificationPoint> points = suspiciousNavigationStrategy
                .getSortedModificationPointsList(this.variants.get(0).getModificationPoints());

        if (points.isEmpty()) {
            log.error("CardumenExportEngine: no modification points found");
            this.outputStatus = AstorOutputStatus.ERROR;
            return;
        }

        String projectDir = projectFacade.getProperties().getOriginalProjectRootDir();
        String toolPath = System.getProperty("cardumen.julia.tool");
        int maxIters = Math.min(points.size(), ConfigurationProperties.getPropertyInt("maxGeneration"));

        outer:
        for (int i = 0; i < maxIters; i++) {
            ModificationPoint target = points.get(i);
            log.info("CardumenExportEngine: iteration " + (i + 1) + "/" + maxIters + " at " + target);

            exportContext(target, projectDir + File.separator + "context.txt");
            exportTargetType(target, projectDir + File.separator + "target_type.txt");

            List<String> candidates;
            if (toolPath != null) {
                candidates = invokeJuliaTool(toolPath, projectDir);
                log.info("CardumenExportEngine: Julia tool returned " + candidates.size() + " candidate(s)");
            } else {
                log.info("CardumenExportEngine: no Julia tool configured, falling back to constant \""
                        + CANDIDATE_EXPRESSION + "\"");
                candidates = new ArrayList<>();
                candidates.add(CANDIDATE_EXPRESSION);
            }

            lastCandidates = candidates;
            for (String candidate : candidates) {
                applyAndTestCandidate(target, candidate);
                if (this.outputStatus == AstorOutputStatus.STOP_BY_PATCH_FOUND) break outer;
            }
        }

        log.info("CardumenExportEngine: export complete");
        if (this.outputStatus == null) {
            this.outputStatus = AstorOutputStatus.EXHAUSTIVE_NAVIGATED;
        }
    }

    /**
     * Writes in-scope variables and reachable methods to context.txt.
     * <p>
     * Format:
     *   # Variables in scope
     *   varName : qualified.Type
     *   ...
     *   # Methods of enclosing class (qualified.ClassName)
     *   methodName(paramType, ...) : returnType
     *   ...
     *   # Methods reachable via in-scope variables
     *   varName.methodName(paramType, ...) : returnType
     *   ...
     */
    private void exportContext(ModificationPoint mp, String filename) throws IOException {
        ContextCounts global = computeCounts(MutationSupporter.getFactory().Type().getAll());
        ContextCounts local  = computeCounts(Collections.<CtType<?>>singletonList(mp.getCtClass()));

        try (BufferedWriter bw = new BufferedWriter(new FileWriter(filename))) {

            // --- Variables in scope ---
            bw.write("# Variables in scope\n");
            List<CtVariable> vars = mp.getContextOfModificationPoint();
            if (vars != null) {
                for (CtVariable<?> var : vars) {
                    String typeName = var.getType() != null
                            ? var.getType().getQualifiedName()
                            : "unknown";
                    String key = var.getSimpleName();
                    bw.write(var.getSimpleName() + " : " + typeName
                            + " : " + global.varCount(key) + " : " + local.varCount(key) + "\n");
                }
            }

            // --- Methods of the enclosing class (callable without a receiver) ---
            bw.write("\n# Methods of enclosing class (" + mp.getCtClass().getQualifiedName() + ")\n");
            Set<CtMethod<?>> classMethods = mp.getCtClass().getMethods();
            for (CtMethod<?> method : classMethods) {
                String key = methodKey(mp.getCtClass().getQualifiedName(), method);
                bw.write(formatMethod(method)
                        + " : " + global.methodCount(key) + " : " + local.methodCount(key) + "\n");
            }

            // --- Methods reachable via in-scope variables ---
            bw.write("\n# Methods reachable via in-scope variables\n");
            if (vars != null) {
                for (CtVariable<?> var : vars) {
                    CtTypeReference<?> typeRef = var.getType();
                    if (typeRef == null) {
                        continue;
                    }
                    CtType<?> typeDecl = typeRef.getTypeDeclaration();
                    if (typeDecl == null) {
                        // Type is from a dependency not in source form; skip.
                        continue;
                    }
                    for (CtMethod<?> method : typeDecl.getMethods()) {
                        String key = methodKey(typeDecl.getQualifiedName(), method);
                        bw.write(var.getSimpleName() + "." + formatMethod(method)
                                + " : " + global.methodCount(key) + " : " + local.methodCount(key) + "\n");
                    }
                }
            }

            // --- Fields of in-scope variables ---
            bw.write("\n# Fields of in-scope variables\n");
            if (vars != null) {
                for (CtVariable<?> var : vars) {
                    CtTypeReference<?> typeRef = var.getType();
                    if (typeRef == null) {
                        continue;
                    }
                    if (typeRef instanceof CtArrayTypeReference) {
                        bw.write(var.getSimpleName() + ".length : int"
                                + " : " + global.fieldCount(ARRAY_LENGTH_KEY)
                                + " : " + local.fieldCount(ARRAY_LENGTH_KEY) + "\n");
                    } else {
                        CtType<?> typeDecl = typeRef.getTypeDeclaration();
                        if (typeDecl == null) {
                            continue;
                        }
                        for (CtField<?> field : typeDecl.getFields()) {
                            String fieldType = field.getType() != null
                                    ? field.getType().getQualifiedName()
                                    : "unknown";
                            String key = fieldKey(typeDecl.getQualifiedName(), field.getSimpleName());
                            bw.write(var.getSimpleName() + "." + field.getSimpleName() + " : " + fieldType
                                    + " : " + global.fieldCount(key) + " : " + local.fieldCount(key) + "\n");
                        }
                    }
                }
            }
        }
        log.info("CardumenExportEngine: context written to " + filename);
    }

    /**
     * Per-scope usage counts for variables, methods, and fields.
     */
    private static final class ContextCounts {
        final Map<String, Integer> vars = new HashMap<>();
        final Map<String, Integer> methods = new HashMap<>();
        final Map<String, Integer> fields = new HashMap<>();

        int varCount(String key)    { return vars.getOrDefault(key, 0); }
        int methodCount(String key) { return methods.getOrDefault(key, 0); }
        int fieldCount(String key)  { return fields.getOrDefault(key, 0); }
    }

    private static void bump(Map<String, Integer> m, String k) {
        m.merge(k, 1, Integer::sum);
    }

    private static String methodKey(String declaringClassFQN, CtMethod<?> method) {
        String params = method.getParameters().stream()
                .map(p -> p.getType() != null ? p.getType().getQualifiedName() : "?")
                .collect(Collectors.joining(","));
        return declaringClassFQN + "#" + method.getSimpleName() + "(" + params + ")";
    }

    private static String methodKey(CtExecutableReference<?> ref) {
        String declaring = ref.getDeclaringType() != null ? ref.getDeclaringType().getQualifiedName() : "?";
        String params = ref.getParameters().stream()
                .map(p -> p != null ? p.getQualifiedName() : "?")
                .collect(Collectors.joining(","));
        return declaring + "#" + ref.getSimpleName() + "(" + params + ")";
    }

    private static String fieldKey(String declaringClassFQN, String fieldName) {
        return declaringClassFQN + "#" + fieldName;
    }

    private static void bumpFieldAccess(Map<String, Integer> fieldCounts, CtFieldReference<?> ref) {
        if (ref == null || ref.getSimpleName() == null) return;
        CtTypeReference<?> declaring = ref.getDeclaringType();
        // Spoon represents `array.length` as a CtFieldRead whose declaring type is the
        // primitive `int` (the field's type), not the array — there's no real `int#length`
        // field in Java, so this pattern uniquely identifies array length accesses.
        boolean isArrayLength = "length".equals(ref.getSimpleName())
                && (declaring == null
                    || declaring instanceof CtArrayTypeReference
                    || "int".equals(declaring.getQualifiedName()));
        if (isArrayLength) {
            bump(fieldCounts, ARRAY_LENGTH_KEY);
        } else if (declaring != null) {
            bump(fieldCounts, fieldKey(declaring.getQualifiedName(), ref.getSimpleName()));
        }
    }

    private ContextCounts computeCounts(Iterable<? extends CtType<?>> types) {
        ContextCounts counts = new ContextCounts();
        TypeFilter<CtVariableAccess> varFilter   = new TypeFilter<>(CtVariableAccess.class);
        TypeFilter<CtInvocation>     invFilter   = new TypeFilter<>(CtInvocation.class);
        TypeFilter<CtFieldRead>      readFilter  = new TypeFilter<>(CtFieldRead.class);
        TypeFilter<CtFieldWrite>     writeFilter = new TypeFilter<>(CtFieldWrite.class);

        for (CtType<?> type : types) {
            if (type == null) continue;

            for (CtVariableAccess<?> va : type.getElements(varFilter)) {
                if (va.getVariable() != null && va.getVariable().getSimpleName() != null) {
                    bump(counts.vars, va.getVariable().getSimpleName());
                }
            }
            for (CtInvocation<?> inv : type.getElements(invFilter)) {
                CtExecutableReference<?> exec = inv.getExecutable();
                if (exec != null && exec.getSimpleName() != null) {
                    bump(counts.methods, methodKey(exec));
                }
            }
            for (CtFieldRead<?> fr : type.getElements(readFilter)) {
                bumpFieldAccess(counts.fields, fr.getVariable());
            }
            for (CtFieldWrite<?> fw : type.getElements(writeFilter)) {
                bumpFieldAccess(counts.fields, fw.getVariable());
            }
        }
        return counts;
    }

    private List<String> invokeJuliaTool(String toolPath, String workingDir) throws IOException, InterruptedException {
        String juliaProject = System.getProperty("cardumen.julia.project");
        ProcessBuilder pb = juliaProject != null
                ? new ProcessBuilder("julia", "--project=" + juliaProject, toolPath, "--production")
                : new ProcessBuilder("julia", toolPath, "--production");
        pb.directory(new File(workingDir));
        pb.redirectErrorStream(false);
        Process proc = pb.start();

        List<String> candidates = new ArrayList<>();
        String outputFile = workingDir + File.separator + "julia_output.txt";
        try (BufferedReader br = new BufferedReader(new InputStreamReader(proc.getInputStream()));
             BufferedWriter out = new BufferedWriter(new FileWriter(outputFile))) {
            String line;
            while ((line = br.readLine()) != null) {
                out.write(line);
                out.newLine();
                if (line.startsWith(CANDIDATE_PREFIX))
                    candidates.add(line.substring(CANDIDATE_PREFIX.length()).trim());
            }
        }
        log.info("CardumenExportEngine: Julia output written to " + outputFile);
        try (BufferedReader err = new BufferedReader(new InputStreamReader(proc.getErrorStream()))) {
            err.lines().forEach(l -> log.warn("julia stderr: " + l));
        }
        int exit = proc.waitFor();
        if (exit != 0) log.error("CardumenExportEngine: Julia tool exited with code " + exit);
        return candidates;
    }

    private void applyAndTestCandidate(ModificationPoint mp, String candidateExpr) throws Exception {
        if (!(mp.getCodeElement() instanceof CtExpression)) {
            log.info("CardumenExportEngine: modification point is not an expression, skipping candidate test");
            return;
        }

        CtExpression<?> candidate =
                MutationSupporter.getFactory().Code().createCodeSnippetExpression(candidateExpr);

        // Capture the original code before applyChangesInModel replaces it in the model.
        String originalCode = mp.getCodeElement().toString();

        ExpressionReplaceOperator op = new ExpressionReplaceOperator();
        OperatorInstance opInstance = new OperatorInstance(mp, op, mp.getCodeElement(), candidate);

        // Record the candidate as its own solution variant (with a distinct id from
        // the original) and register the operation on it. This is what lets the
        // standard atEnd() flow write a diffSolutions folder and a non-empty
        // patches[] in astor_output.json when the candidate passes the tests.
        ProgramVariant parent = this.variants.get(0);
        this.generationsExecuted++;
        ProgramVariant solutionVariant =
                variantFactory.createProgramVariantFromAnother(parent, generationsExecuted);
        solutionVariant.getOperations().put(generationsExecuted, Arrays.asList(opInstance));

        boolean applied = op.applyChangesInModel(opInstance, solutionVariant);
        if (!applied) {
            log.error("CardumenExportEngine: failed to apply candidate \"" + candidateExpr + "\"");
            return;
        }

        log.info("CardumenExportEngine: original code at suspicious location: \"" + originalCode + "\"");
        log.info("CardumenExportEngine: testing candidate expression \"" + candidateExpr + "\"");

        boolean passes;
        try {
            passes = processCreatedVariant(solutionVariant, generationsExecuted);
        } finally {
            // Revert the shared Spoon model before serializing: savePatch re-saves the
            // original variant from the current model, so the change must be undone
            // first or the computed diff would be empty.
            op.undoChangesInModel(opInstance, solutionVariant);
        }

        if (passes) {
            log.info("CardumenExportEngine: candidate PASSES tests — patch accepted");
            this.solutions.add(solutionVariant);
            this.savePatch(solutionVariant);
            this.outputStatus = AstorOutputStatus.STOP_BY_PATCH_FOUND;
        } else {
            log.info("CardumenExportEngine: candidate FAILS tests");
        }
    }

    private String formatMethod(CtMethod<?> method) {
        String returnType = method.getType() != null
                ? method.getType().getQualifiedName()
                : "void";
        String params = method.getParameters().stream()
                .map(p -> p.getType().getQualifiedName())
                .collect(Collectors.joining(", "));
        return method.getSimpleName() + "(" + params + ") : " + returnType;
    }

    /**
     * Writes the suspicious location and the type of the targeted code element
     * to target_type.txt.
     * <p>
     * Format:
     *   class: qualified.ClassName
     *   line: N
     *   suspiciousness: 0.xxx
     *   element: <source text of the element>
     *   type: qualified.TypeName   (or "not-an-expression" when the element has no type)
     */
    private void exportTargetType(ModificationPoint mp, String filename) throws IOException {
        try (BufferedWriter bw = new BufferedWriter(new FileWriter(filename))) {
            SuspiciousModificationPoint smp = (SuspiciousModificationPoint) mp;

            bw.write("class: " + mp.getCtClass().getQualifiedName() + "\n");
            bw.write("line: " + smp.getSuspicious().getLineNumber() + "\n");
            bw.write("suspiciousness: " + smp.getSuspicious().getSuspiciousValue() + "\n");
            bw.write("element: " + mp.getCodeElement().toString() + "\n");

            if (mp.getCodeElement() instanceof CtExpression) {
                CtTypeReference<?> type = ((CtExpression<?>) mp.getCodeElement()).getType();
                bw.write("type: " + (type != null ? type.getQualifiedName() : "unknown") + "\n");
            } else {
                bw.write("type: not-an-expression\n");
            }
        }
        log.info("CardumenExportEngine: target type written to " + filename);
    }
}
